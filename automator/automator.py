"""
Evaluation Automator — Orchestrates multimodal AI agent evaluations.

This module is the entry point for running evaluations. It:
  1. Manages evaluation lifecycle (setup, execution, cleanup)
  2. Launches XRClaw instrumentation on companion device
  3. Spawns coordinator and worker processes (agent_tester, judge_worker)
  4. Handles multi-round evaluation with automatic retry of failed queries
  5. Supports re-evaluation mode for targeted re-testing
  6. Generates reports and visualizations

Usage:
    python -m automator.automator configs/your_config.json

Process Architecture:
    automator.py (orchestrator)
       ├── metric_coordinator.coordinator (HOST process)
       ├── agent_testers.agent_tester (CLIENT in screen session)
       └── judge_worker.judge_worker (CLIENT in screen session)
"""

import os, subprocess, shutil, json, time, datetime, sys, glob
from copy import deepcopy
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt
import pandas as pd

from utils.file_utils import *
from common.test_groups import resolve_config_groups, filter_dataset_by_group, list_groups, TEST_GROUPS
import automator


DIR = os.getcwd()
ENV = sys.prefix

class EvaluationAutomator:
    """
    Orchestrates evaluation runs for multimodal AI agents.
    
    Responsibilities:
      - Validate and manage config (handle re-evaluation mode)
      - Protect against accidental overwrites of completed runs
      - Launch XRClaw instrumentation before evaluation
      - Spawn coordinator and worker processes in screen sessions
      - Manage multi-round evaluation (retry failed queries)
      - Clean up and prepare datasets for each round
      - Generate per-round reports with bad response analysis
    """
    def __init__(self, config_path: str):
        self.config_baseline = JSONFileManager.load_file(config_path)
        assert self.config_baseline["dataset_start_index"] <= self.config_baseline["dataset_end_index"], "Invalid start and end indices"
        self._resume_partial_run = False

        # ── Auto-compute re-evaluation indices from test_groups ──
        # If test_groups is set but reevaluation_question_indices is not,
        # auto-populate the indices from the dataset. This makes test group
        # runs use the re-evaluation path (preserve existing data, append
        # results) instead of triggering the overwrite prompt.
        reeval_indices = self.config_baseline.get("reevaluation_question_indices", [])
        test_groups = resolve_config_groups(self.config_baseline)
        if test_groups and not reeval_indices:
            _, original_dataset = JSONLFileManager.load_file(
                self.config_baseline["paths"]["dataset_file"]
            )
            auto_indices = []
            for idx, entry in enumerate(original_dataset):
                qt = (entry.get("question_type", "")).lower()
                for g in test_groups:
                    matched = False
                    for pattern in TEST_GROUPS[g].patterns:
                        if pattern in qt:
                            auto_indices.append(idx)
                            matched = True
                            break
                    if matched:
                        break
            self.config_baseline["reevaluation_question_indices"] = auto_indices
            print(f"\nTest groups {test_groups} → {len(auto_indices)} re-evaluation indices "
                  f"(auto-computed, preserving existing data)")

        # Check if re-evaluation mode is active
        is_reeval_mode = self.config_baseline.get("reevaluation_question_indices", []) and len(self.config_baseline.get("reevaluation_question_indices", [])) > 0

        root_folder = self.config_baseline["paths"]["root_folder"]

        # In re-evaluation mode, preserve existing results (don't delete root_folder)
        if not is_reeval_mode:
            if os.path.exists(root_folder):
                has_completed_report = os.path.exists(os.path.join(root_folder, "vqa_report.jsonl"))

                # Non-interactive: refuse to overwrite to prevent data loss
                if not sys.stdin.isatty():
                    raise FileExistsError(
                        f"root_folder '{root_folder}' already contains a "
                        f"{'completed' if has_completed_report else 'partial'} run. "
                        f"Cannot prompt in non-interactive mode."
                    )

                if has_completed_report:
                    while True:
                        response = input(f"root_folder has a completed run. Overwrite? (y/n): ").strip().lower()
                        if response in ("y", "n"):
                            break
                    if response == "n":
                        raise FileExistsError("Refusing to overwrite — pick a new root_folder or remove the old one.")
                    else:
                        ## Clean up folders to start new evaluation
                        shutil.rmtree(root_folder)
                else:
                    # Partial/crashed run — ask whether to resume or overwrite
                    while True:
                        response = input(f"root_folder has a partial run. Continue (c) or overwrite (o)? ").strip().lower()
                        if response in ("c", "o"):
                            break
                    if response == "o":
                        shutil.rmtree(root_folder)
                    else:
                        self._resume_partial_run = True
                        return  # skip folder creation — evaluate() will resume

        os.makedirs(self.config_baseline["paths"]["root_folder"], exist_ok = True)
        shutil.copy(self.config_baseline["paths"]["dataset_file"], self.config_baseline["paths"]["root_folder"] + "/")
    
    def start_xrclaw(self):
        """Launch XRClaw with ShellIdentityInstrumentation on the companion device.

        This must be done BEFORE starting agent_tester, because agent_tester's
        __init__ creates the XRClawStateCollector which requires the instrumentation
        to be running on the companion device.
        """
        xrclaw_config = self.config_baseline.get("xrclaw", {})
        if not xrclaw_config.get("enabled", False):
            print("XRClaw is disabled in config — skipping instrumentation startup.")
            return

        companion_device = self.config_baseline["devices"].get("s25_device_id", "")
        if not companion_device:
            print("WARNING: No s25_device_id found in config — cannot start XRClaw.")
            return

        claw_package = xrclaw_config.get("claw_package", "com.samsung.xr.claw.client")

        print(f"Starting XRClaw instrumentation on {companion_device}...")

        # Force-stop any existing instance first
        subprocess.run(
            f"adb -s {companion_device} shell am force-stop {claw_package}",
            shell=True
        )
        time.sleep(1)

        # Start instrumentation in the background (am instrument -w blocks,
        # so we use Popen to keep it running without blocking the automator)
        proc = subprocess.Popen(
            [
                "adb", "-s", companion_device, "shell",
                "am", "instrument", "-w",
                f"{claw_package}/.ShellIdentityInstrumentation"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Give the instrumentation time to initialize
        time.sleep(3)

        # Verify it started
        verify = subprocess.run(
            f"adb -s {companion_device} shell dumpsys activity processes | grep {claw_package}",
            shell=True, capture_output=True, text=True
        )
        if claw_package in verify.stdout:
            print(f"XRClaw instrumentation started successfully on {companion_device}")
        else:
            print(f"WARNING: XRClaw instrumentation may not have started on {companion_device}. "
                  f"State collection may fail. Check device logs.")

    def run_evaluation(self, config_path: str) -> None:
        """Spawn coordinator and worker processes for evaluation.

        Launches three processes:
          1. metric_coordinator.coordinator — Host process that reads dataset,
             dispatches work to clients, and persists results to SQLite queue.
          2. agent_testers.agent_tester — Client in screen session that executes
             queries on devices via XRClaw and captures state.
          3. judge_worker.judge_worker — Client in screen session that evaluates
             responses using deterministic rules or VLM judge.

        Processes communicate via named pipes (FIFOs) in /tmp. Screen sessions
        allow processes to persist independently of the automator.

        Args:
            config_path: Path to the evaluation config JSON for this round.
        """
        # start host servers
        coordinator = subprocess.Popen([
            "bash", "-c",
            f"python -m metric_coordinator.coordinator {config_path}"
        ])

        # start client servers
        config = JSONFileManager.load_file(config_path)
        dashboard_config = config.get("dashboard", {"enabled": True, "port": 5055})
        
        screens = [
            ("agent_tester", f"python -m agent_testers.agent_tester {config_path}"),
            ("judge_worker", f"python -m judge_worker.judge_worker {config_path}"),
        ]
        
        # Add eval dashboard if enabled
        if dashboard_config.get("enabled", True):
            dashboard_port = dashboard_config.get("port", 5055)
            screens.append(("eval_dashboard", f"python -m services.client.eval_dashboard --db metric_coordinator/queue.db --port {dashboard_port}"))
        for name, cmd in screens:
            # kill existing screen if any
            subprocess.run( f"screen -list | grep -E '[0-9]+\\.{name}[[:space:]]' | awk '{{print $1}}' | while read sid; do screen -S \"$sid\" -X quit; done", shell=True)

            # start new persistent screen
            subprocess.run([
                "screen", "-dmS", name,
                "bash", "-c",
                f"cd {DIR} && source {ENV}/bin/activate && {cmd}; exec bash"
            ])

        coordinator.wait()

    @staticmethod
    def _cleanup_for_reevaluation(reeval_indices: list, dataset: list,
                                   num_evaluations: int, root_folder: str) -> None:
        """
        Clean up assets and report entries for specified question indices across all eval folders.
        Uses recursive glob to find and delete files matching the qid pattern.

        Args:
            reeval_indices: List of indices (relative to current dataset) to re-evaluate
            dataset: Current round's dataset containing eval_id for each question
            num_evaluations: Total number of evaluation rounds
            root_folder: Root folder path containing all eval_set folders
        """
        if not reeval_indices or len(reeval_indices) == 0:
            return

        # Extract eval_ids (qids) for indices to re-evaluate
        qids_to_delete = set()
        for idx in reeval_indices:
            if idx < len(dataset):
                qids_to_delete.add(dataset[idx]["eval_id"])

        if not qids_to_delete:
            return

        print(f"Cleaning up for re-evaluation: {len(qids_to_delete)} qids")

        # For each eval_set folder (1 to num_evaluations)
        for round_num in range(1, num_evaluations + 1):
            eval_folder = os.path.join(root_folder, f"eval_set_{round_num}")
            if not os.path.exists(eval_folder):
                continue

            # Use recursive glob from eval_folder root to find all files
            for file_path in glob.glob(os.path.join(eval_folder, "**", "*"), recursive=True):
                if os.path.isfile(file_path):
                    filename = os.path.basename(file_path)
                    # Check if filename contains any qid to delete
                    for qid in qids_to_delete:
                        if qid.replace('q', '') in filename:
                            os.remove(file_path)
                            print(f"  Deleted: {file_path}")
                            break  # Found match, no need to check other qids

            # Filter vqa_report.jsonl - remove lines with matching eval_ids
            vqa_report_path = os.path.join(eval_folder, "vqa_report.jsonl")
            if os.path.exists(vqa_report_path):
                header, data = JSONLFileManager.load_file(vqa_report_path)
                filtered_data = [d for d in data if d["eval_id"] not in qids_to_delete]
                if len(filtered_data) < len(data):
                    JSONLFileManager.dump_file(header, filtered_data, vqa_report_path)
                    print(f"  Removed {len(data) - len(filtered_data)} entries from vqa_report.jsonl in eval_set_{round_num}")

    def prepare_iter_dataset(self, round_num: int, reeval_indices: list = None):
        """
        Prepare dataset for an evaluation round.

        Args:
            round_num: Current round number (1-indexed)
            reeval_indices: List of indices to re-evaluate (relative to previous round's dataset)
                           If None or empty, use normal flow based on start/end indices
        """
        # Check if re-evaluation mode is active
        is_reeval_mode = reeval_indices is not None and len(reeval_indices) > 0

        eval_folder_name = f"eval_set_{round_num}"
        eval_folder_path = os.path.join(self.config_baseline["paths"]["root_folder"], eval_folder_name)
        dataset_name = self.config_baseline["paths"]["dataset_file"].split("/")[-1]
        dataset_size = 0

        # Get header from original dataset
        original_header, _ = JSONLFileManager.load_file(self.config_baseline["paths"]["dataset_file"])

        # update and dump new config in eval folder
        new_config = deepcopy(self.config_baseline)
        new_config["paths"]["dataset_file"] = os.path.join(eval_folder_path, dataset_name)
        new_config["paths"]["root_folder"] = eval_folder_path

        # For round > 1, check if there are any failed queries before creating the folder
        if round_num > 1:
            last_eval_folder_name = f"eval_set_{round_num - 1}"
            last_eval_folder_path = os.path.join(self.config_baseline["paths"]["root_folder"], last_eval_folder_name)

            _, vqa_report = JSONLFileManager.load_file(os.path.join(last_eval_folder_path, "vqa_report.jsonl"))
            header, dataset = JSONLFileManager.load_file(os.path.join(last_eval_folder_path, dataset_name))

            last_itr_config = JSONFileManager.load_file(os.path.join(last_eval_folder_path, "eval_config.json"))

            vqa_report_dict = {line["eval_id"]: line for line in vqa_report}
            print(os.path.join(last_eval_folder_path, dataset_name), round_num)
            missing_eval_ids = [
                line["eval_id"] for line in dataset[last_itr_config["dataset_start_index"]: last_itr_config["dataset_end_index"] + 1]
                if line["eval_id"] not in vqa_report_dict
            ]
            if missing_eval_ids:
                # A query that crashed/timed out in the previous round never made it
                # into vqa_report.jsonl. Treat it as "needs retry" like a bad rating,
                # instead of KeyError-ing here and truncating the whole run's report
                # to only the rounds that completed before the crash.
                print(f"Round {round_num}: {len(missing_eval_ids)} eval_id(s) missing from previous round's report "
                      f"(crashed/timed out) — retrying: {missing_eval_ids}")
            filtered_dataset = [line for line in dataset[last_itr_config["dataset_start_index"]: last_itr_config["dataset_end_index"] + 1] if (line["eval_id"] not in vqa_report_dict) or ((vqa_report_dict[line["eval_id"]]["rating"] is None) or (vqa_report_dict[line["eval_id"]]["rating"] < 3))] #only the bad responses (or missing/crashed ones) are kept in the new round

            dataset_size = len(filtered_dataset)
            
            # If all queries passed, don't create the folder and return early
            if dataset_size == 0:
                print(f"Round {round_num}: All queries passed (rating >= 3)! Stopping evaluation.")
                return None, 0
            
            # Only create folder if there's data to process
            os.makedirs(eval_folder_path, exist_ok=True)
            
            JSONLFileManager.dump_file(header, filtered_dataset, os.path.join(eval_folder_path, dataset_name))
            new_config["dataset_start_index"] = 0
            new_config["dataset_end_index"] = int(1e5)
        elif is_reeval_mode and round_num == 1:
            # RE-EVALUATION MODE, Round 1: Filter original dataset to specified indices
            _, original_dataset = JSONLFileManager.load_file(self.config_baseline["paths"]["dataset_file"])
            filtered_dataset = [original_dataset[idx] for idx in reeval_indices if idx < len(original_dataset)]

            os.makedirs(eval_folder_path, exist_ok=True)
            JSONLFileManager.dump_file(original_header, filtered_dataset, os.path.join(eval_folder_path, dataset_name))
            dataset_size = len(filtered_dataset)
            new_config["dataset_start_index"] = 0
            new_config["dataset_end_index"] = len(filtered_dataset) - 1 if filtered_dataset else 0
        else:
            # NORMAL MODE, Round 1: Copy original dataset (coordinator uses start/end indices for iteration)
            if os.path.exists(eval_folder_path):
                shutil.rmtree(eval_folder_path)
            os.makedirs(eval_folder_path)

            shutil.copy(self.config_baseline["paths"]["dataset_file"], eval_folder_path)

            _, dataset = JSONLFileManager.load_file(os.path.join(eval_folder_path, dataset_name))

            # ── Test group filtering ──────────────────────────────────
            # If "test_groups" is set in config, filter the dataset to only
            # include entries matching the selected app function groups.
            # This allows targeted testing of specific features (volume, camera,
            # notes, etc.) without running the full dataset.
            test_groups = resolve_config_groups(self.config_baseline)
            if test_groups:
                print(f"\n{'='*60}")
                print(f"Test group filtering enabled: {', '.join(test_groups)}")
                print(f"Available groups: {', '.join(list_groups())}")
                print(f"Dataset before filtering: {len(dataset)} entries")

                header, _ = JSONLFileManager.load_file(os.path.join(eval_folder_path, dataset_name))
                filtered_dataset = filter_dataset_by_group(dataset, test_groups)

                print(f"Dataset after filtering:  {len(filtered_dataset)} entries")
                if not filtered_dataset:
                    print("WARNING: No dataset entries match the selected test groups!")
                    print("Check that the question_type patterns in the dataset match the group patterns.")
                else:
                    # Show breakdown by group
                    from common.test_groups import get_group_for_question_type
                    group_counts: dict[str, int] = {}
                    for entry in filtered_dataset:
                        g = get_group_for_question_type(entry.get("question_type", ""))
                        if g:
                            group_counts[g] = group_counts.get(g, 0) + 1
                    for g, count in sorted(group_counts.items()):
                        print(f"  {g}: {count} entries")
                    print()

                    # Overwrite the dataset file with the filtered version
                    JSONLFileManager.dump_file(header, filtered_dataset, os.path.join(eval_folder_path, dataset_name))
                    dataset = filtered_dataset

            dataset_size = len(dataset)

        new_config_path = os.path.join(eval_folder_path, "eval_config.json")
        JSONFileManager.dump_file(new_config, new_config_path)

        return new_config_path, dataset_size

    def prepare_iter_report(self, round_num: int, append_to_existing: bool = False) -> None:  
        """
        Prepare report for an evaluation round.

        Args:
            round_num: Current round number (1-indexed)
            append_to_existing: If True, append new entries to existing vqa_report.jsonl
        """
        eval_folder_name = f"eval_set_{round_num}"
        eval_folder_path = os.path.join(self.config_baseline["paths"]["root_folder"], eval_folder_name)

        current_config_path = os.path.join(eval_folder_path, "eval_config.json")
        current_config = JSONFileManager.load_file(current_config_path)
        
        shutil.copy(current_config["paths"]["queue_file"], eval_folder_path)
        queue_name = current_config["paths"]["queue_file"].split("/")[-1]
        queue_path = os.path.join(eval_folder_path, queue_name)
        
        report_gen = automator.ReportGenerator(queue_path)
        report_gen.generate_json_report(append_to_existing=append_to_existing)
            
        header, data = JSONLFileManager.load_file(f"{eval_folder_path}/vqa_report.jsonl")
        
        with open(f"{eval_folder_path}/bad_responses.txt", 'w') as bad_response_file:
            bad_indices = []
            for i, data_info in enumerate(data):
                if data_info["rating"] is None or str(data_info["rating"]).strip() in ['N/A', 'null', ''] or int(data_info["rating"]) < 3:
                    bad_response_file.write("%d, %s\n"%(i, data_info["eval_id"]))
                    bad_response_file.write("%s\n"%data_info["question"]); bad_response_file.write("%s\n"%data_info["gt_answer"])
                    bad_response_file.write("%s\n"%data_info["ai_response"]); bad_response_file.write("%s\n"%data_info["rating"])
                    bad_response_file.write("\n")
                    bad_indices.append(data_info['eval_id'])  
                    
            bad_response_file.write("\n%s\n"%", ".join(bad_indices)); bad_response_file.write("%d\n"%len(bad_indices))
            
    def evaluate(self):
        """Execute the full evaluation pipeline.

        Pipeline:
          1. Start XRClaw instrumentation (required for app state collection)
          2. For each evaluation round:
             a. Prepare dataset (filter failed queries from previous round)
             b. Launch coordinator and workers
             c. Wait for coordinator to complete
             d. Generate round report with bad response analysis
          3. Support re-evaluation mode for targeted re-testing

        Re-evaluation mode: When `reevaluation_question_indices` is set in config,
        only those specific questions are re-tested, preserving other results.
        """
        # Start XRClaw instrumentation on companion device before any evaluation
        # agent_tester's __init__ creates XRClawStateCollector which needs it running
        self.start_xrclaw()

        # Get re-evaluation indices from config (empty list = normal flow)
        reeval_indices = self.config_baseline.get("reevaluation_question_indices", [])

        # Determine if re-evaluation mode is active
        is_reeval_mode = reeval_indices is not None and len(reeval_indices) > 0

        # Cleanup before first round if re-evaluation mode is active
        if is_reeval_mode:
            _, original_dataset = JSONLFileManager.load_file(self.config_baseline["paths"]["dataset_file"])

            ## Remove existing evaluation files cached but only for the reeval qids
            self._cleanup_for_reevaluation(
                reeval_indices,
                original_dataset,
                self.config_baseline["automator"]["num_evaluations"],
                self.config_baseline["paths"]["root_folder"]
            )

        for round_num in tqdm(range(1, self.config_baseline["automator"]["num_evaluations"] + 1)):
            try:
                config_path, dataset_size = self.prepare_iter_dataset(round_num, reeval_indices)
                if dataset_size:
                    self.run_evaluation(config_path)
                    print("Starting Postprocessing")
                    # In re-eval mode, append new entries to existing report
                    self.prepare_iter_report(round_num, append_to_existing=is_reeval_mode)
                else:
                    print(f"Round {round_num}: No samples to evaluate (all passed or dataset empty). Stopping evaluation.")
                    break
            except Exception as e:
                import traceback
                print(f"Round {round_num} failed with error: {e}")
                traceback.print_exc()
                print(f"Stopping evaluation after {round_num - 1} completed rounds.")
                break

            

class PostProcessAutomator:
    """
    Post-processes evaluation results and generates reports.

    Responsibilities:
      - Merge multi-round results (select best rating per query)
      - Generate consolidated vqa_report.jsonl
      - Compute summary statistics (hit rate, stability, latency, power)
      - Generate visualizations (category-wise bar charts, bad iteration plots)
      - Generate XR Board and KPI reports
      - Backup results to configured backup folder
    """
    def __init__(self, config_path: str):
        """Initialize post-processor with evaluation config.

        Args:
            config_path: Path to the evaluation config JSON.
        """
        self.config_path = config_path
        self.data_config = JSONFileManager.load_file(config_path)
        self.root_folder_path = self.data_config["paths"]["root_folder"]
        self.n_eval = self.data_config["automator"]["num_evaluations"]

        dataset_name = self.data_config["paths"]["dataset_file"].split("/")[-1]
        version = ".".join(dataset_name.split("_")[-1].split(".")[:-1])
    
    def sort_responses(self, report_files):
        """Merge and sort responses from multiple evaluation rounds.

        For each question, collects all round responses and sorts by rating
        (descending) to select the best response.

        Args:
            report_files: List of vqa_report.jsonl paths from each round.

        Returns:
            Tuple of (header, responses_dict) where responses_dict maps
            eval_id to list of responses sorted by rating (best first).
        """
        responses = {}; header = {}
        for eval_idx in range(len(report_files)):
            eval_lines = open(report_files[eval_idx], 'r').read().split("\n")[:-1]; eval_lines = [json.loads(eval_lines[i]) for i in range(len(eval_lines))]
            header = eval_lines[0]
            for data_info in eval_lines[1:]:
                responses[data_info['eval_id']] = responses.get(data_info['eval_id'], [])
                if str(data_info["rating"]).strip() in ['N/A', 'None', '']:
                    data_info["rating"] = '0'
                data_info["iteration"] = eval_idx + 1
                responses[data_info['eval_id']].append(data_info)
        
        for eval_id in responses:
            responses[eval_id] = sorted(responses[eval_id], reverse= True, key = lambda x: int(x["rating"]))
        return header, responses    
        
    def analyze_response(self):
        """Merge per-round reports into consolidated vqa_report.jsonl.

        Collects vqa_report.jsonl from all eval_set folders, merges responses
        for each question (keeping all rounds), and writes to root folder.
        Adds iteration metadata to track which round each response came from.
        """
        report_files = [os.path.join(self.root_folder_path, f"eval_set_{indx}", "vqa_report.jsonl") for indx in range(1, self.n_eval+1) if os.path.exists(os.path.join(self.root_folder_path, f"eval_set_{indx}", "vqa_report.jsonl"))]
        if not report_files:
            print("No vqa_report.jsonl files found — nothing to analyze.")
            return
        header, responses = self.sort_responses(report_files)

        header["fields"]["iteration"] = "Iteration of the evaluation round"       
            
        eval_json_file = open(os.path.join(self.root_folder_path, "vqa_report.jsonl"), 'w')
        eval_json_file.write(json.dumps(header) + "\n")
        eval_ids = list(responses.keys()); eval_ids.sort()
        for eval_id in eval_ids:
            eval_json_file.write(json.dumps(responses[eval_id]) + "\n")    
        
    def render_report_func(self, out_dir):
        """Generate HTML visual reports.

        Renders the consolidated vqa_report.jsonl into chunked HTML files
        (25 samples per file) for interactive browsing.

        Args:
            out_dir: Output directory for HTML report files.
        """
        renderer = automator.SummaryRenderer(jsonl_path = f"{out_dir}/vqa_report.jsonl", output_dir = out_dir)
        renderer.write_report()
        jsonl_path = f"{out_dir}/vqa_report.jsonl"
        header, samples = renderer.load_jsonl(jsonl_path)
        chunk_size = 25
        for start in range(0, len(samples), chunk_size):
            output_path = f"{out_dir}/report_visual_{start}_to_{start+chunk_size}.html"
            print("rendering", output_path)
            automator.render_part_html(header, samples[start:start+chunk_size], output_path)
              
    def generate_output_csv(self, ):
        """Generate summary statistics and visualizations.

        Computes per-eval_type metrics:
          - Hit Rate @ N (fraction passing by round N)
          - Mean Stability Score (weighted by round)
          - Mean Rating (best per query)
          - Mean Latency (response time)
          - Mean Power (if power metrics available)

        Generates:
          - summary_report.txt — Text summary of all metrics
          - {eval_type}_category_wise.png — Bar chart by question_type
          - bad_iterations.png — Bar chart of failures by round, per eval_type
        """
        _, report =  JSONLFileManager.load_file(os.path.join(self.root_folder_path, "vqa_report.jsonl"))
        #Summary Report
        summary_report = {}

        eval_ids = [data[0]["eval_id"] for data in report]; report_dict = {data[0]["eval_id"]: data for data in report}
        
        exp_name = self.data_config["paths"]["dataset_file"].split("/")[-2]
        textual_summary = open(os.path.join(self.root_folder_path, "summary_report.txt"), 'w')
        ratings = []; overall_times = []; qa_times =[]; vqa_times = []; hallucination_times = []
        for eval_id in eval_ids:
            eval_q_rounds = report_dict[eval_id]
            summary_report[eval_q_rounds[0]["eval_type"]] = summary_report.get(eval_q_rounds[0]["eval_type"], dict())
            summary_report[eval_q_rounds[0]["eval_type"]]["bad_iterations"] = summary_report[eval_q_rounds[0]["eval_type"]].get("bad_iterations", {})

            best_iteration = feasible_iteration = -1; best_rating = 0; response_time = None
            for q_round in eval_q_rounds:
                if int(q_round["rating"]) > 2:
                    if feasible_iteration == -1 or feasible_iteration > q_round["iteration"]:
                        feasible_iteration = q_round["iteration"]
                else:
                    summary_report[eval_q_rounds[0]["eval_type"]]["bad_iterations"][q_round["iteration"]] = summary_report[eval_q_rounds[0]["eval_type"]]["bad_iterations"].get(q_round["iteration"], 0) + 1
                if best_iteration == -1 or (int(q_round["rating"]) > best_rating and q_round["iteration"] < best_iteration):
                    best_rating = int(q_round["rating"])
                    best_iteration = q_round["iteration"]
                    response_time = q_round["response_time"]

            summary_report[eval_q_rounds[0]["eval_type"]]["feasible_iteration"] = summary_report.get(eval_q_rounds[0]["eval_type"], dict()).get("feasible_iteration", [])
            summary_report[eval_q_rounds[0]["eval_type"]]["feasible_iteration"].append(int(feasible_iteration))
            summary_report[eval_q_rounds[0]["eval_type"]]["best_iteration"] = summary_report.get(eval_q_rounds[0]["eval_type"], dict()).get("best_iteration", [])
            summary_report[eval_q_rounds[0]["eval_type"]]["best_iteration"].append(int(best_iteration))
            summary_report[eval_q_rounds[0]["eval_type"]]["best_rating"] = summary_report.get(eval_q_rounds[0]["eval_type"], dict()).get("best_rating", [])
            summary_report[eval_q_rounds[0]["eval_type"]]["best_rating"].append(int(best_rating))
            summary_report[eval_q_rounds[0]["eval_type"]]["response_time"] = summary_report.get(eval_q_rounds[0]["eval_type"], dict()).get("response_time", [])
            summary_report[eval_q_rounds[0]["eval_type"]]["response_time"].append(float(response_time) if response_time else None)
            summary_report[eval_q_rounds[0]["eval_type"]]["category_wise"] = summary_report.get(eval_q_rounds[0]["eval_type"], dict()).get("category_wise", dict())
            summary_report[eval_q_rounds[0]["eval_type"]]["category_wise"][eval_q_rounds[0]["question_type"]] = summary_report[eval_q_rounds[0]["eval_type"]]["category_wise"].get(eval_q_rounds[0]["question_type"], [])
            summary_report[eval_q_rounds[0]["eval_type"]]["category_wise"][eval_q_rounds[0]["question_type"]].append(best_rating)
            
            # Collect power values
            pm = eval_q_rounds[0].get("meta_info", {}).get("power_metrics") or {}
            if pm.get("avg_power_w") is not None:
                summary_report[eval_q_rounds[0]["eval_type"]]["power"] = summary_report[eval_q_rounds[0]["eval_type"]].get("power", [])
                summary_report[eval_q_rounds[0]["eval_type"]]["power"].append(float(pm["avg_power_w"]))
        
        # print(summary_report)
        for eval_type in summary_report:
            values, counts = np.unique(summary_report[eval_type]["feasible_iteration"], return_counts = True)

            total_passes = 0
            for iter_num, count in zip(values, counts):
                if iter_num <= 0:
                    continue
                total_passes += count
                textual_summary.write(f"{eval_type}: Hit Rate @ {iter_num}: {total_passes/np.sum(counts)}\n")
            
            stability_score_mapping = {
                1: 1.0,
                2: 0.67,
                3: 0.5,
                4: 0.4,
                5: 0.33, 
                6: 0.25, 
                7: 0.20
            }
            all_stability_scores = [stability_score_mapping.get(itr, 0) for itr in summary_report[eval_type]["feasible_iteration"]]
            textual_summary.write(f"{eval_type}: Mean Stability Score: {round(np.mean(all_stability_scores), 2)}\n")

            textual_summary.write(f"{eval_type}: Mean Rating: {round(np.mean(summary_report[eval_type]['best_rating']), 2)}\n")

            textual_summary.write(f"{eval_type}: Mean Latency: {round(np.nanmean(np.array(summary_report[eval_type]['response_time']), dtype = float), 2)}\n")
            
            if summary_report[eval_type].get("power"):
                textual_summary.write(f"{eval_type}: Mean Power: {round(np.mean(summary_report[eval_type]['power']), 3)} W\n")

            plt.figure()
            categories = list(summary_report[eval_type]["category_wise"].keys())
            values = [round(np.mean(x), 2) for x in summary_report[eval_type]["category_wise"].values()]
            fig, ax = plt.subplots()
            bars = ax.bar(categories, values)
            ax.bar_label(bars, padding=3)
            plt.xticks(rotation = 45, fontsize = 9, ha = "right")
            plt.savefig(os.path.join(self.root_folder_path, f"{eval_type}_category_wise.png"), dpi=300, bbox_inches='tight')
        
        textual_summary.close()
        
        plt.figure()
        df = pd.DataFrame({eval_type: summary_report[eval_type]["bad_iterations"]  for eval_type in summary_report})
        if not df.empty:
            ax = df.plot.bar(rot=0)
            for container in ax.containers:
                ax.bar_label(container, padding=3)
            plt.tight_layout()
            plt.savefig(os.path.join(self.root_folder_path, "bad_iterations.png"), dpi=300, bbox_inches='tight')
        else:
            print("NO BAD RESPONSES! HENCE NO BAR PLOT!")

                
    def generate_reports(self):
        """Generate all evaluation reports and artifacts.

        Pipeline:
          1. Merge per-round reports (analyze_response)
          2. Generate HTML visual reports (chunked by 25 samples)
          3. Generate summary statistics and plots (generate_output_csv)
          4. Generate XR Board and KPI reports (if configured)
          5. Backup results to backup_folder_path (if configured)

        XR Board reports:
          - XR_Board format (jinju/gemini-live-s25 only)
          - KPI formats for QA_TASK, Visual_QA_TASK, Hallucination_TASK

        Backups are timestamped to preserve history across runs.
        """
        if self.data_config["automator"]["generate_reports"]:
            print("Generating reports!")
            self.analyze_response()

        # Guard against missing vqa_report.jsonl (e.g. all rounds failed/crashed)
        vqa_path = os.path.join(self.root_folder_path, "vqa_report.jsonl")
        if not os.path.exists(vqa_path):
            print("No vqa_report.jsonl found — skipping report rendering and CSV generation.")
            return

        self.render_report_func(self.root_folder_path)
        self.generate_output_csv()

        
        if self.data_config["automator"]["xr_board"]["generate_reports"]:
            print("Generating XR reports!")
            eval_json_path = self.root_folder_path + "/vqa_report.jsonl"
            companion_pair = self.data_config["automator"]["xr_board"]["companion_pair"]

            file_paths = []
            if companion_pair == "jinju/gemini-live-s25":
                automator.XR_Board_report_generator(eval_json_path, self.config_path, True)
                file_paths.append(eval_json_path.rsplit('.',1)[0] + "_for_XRBoard.json")
            automator.KPI_Test_report_generator(eval_json_path, self.config_path, True)

            for new_name in ["_for_KPI_QA_TASK.json", "_for_KPI_Visual_QA_TASK.json", "_for_KPI_Hallucination_TASK.json"]:
                file_paths.append(eval_json_path.rsplit('.',1)[0] + new_name)
            
            if self.data_config["automator"]["xr_board"]["upload_files"]:
                uploaded_files = {}
                for fp in file_paths:
                    uploaded_files = automator.scan_and_upload_file(fp, True, uploadnned_files = uploaded_files) 
        
        if os.path.isdir(self.data_config["paths"]["backup_folder_path"]):
            shutil.copytree(self.data_config["paths"]["root_folder"],
                os.path.join(self.data_config["paths"]["backup_folder_path"], self.data_config["paths"]["root_folder"].rsplit('/', 1)[-1] + "_" + str(int(time.time() * 1000))))

if __name__ == "__main__":    
    config_path = sys.argv[1]
    config = JSONFileManager.load_file(config_path)

    if not config["automator"]["postprocess_only"]:
        eval_automator = EvaluationAutomator(config_path)
        eval_automator.evaluate()

    postprocess_setup = PostProcessAutomator(config_path)
    postprocess_setup.generate_reports()
