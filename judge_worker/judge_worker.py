import json, sys, os
import logging

from judge_worker.response_scorer import ResponseScorer
from utils.file_utils import JSONFileManager
from utils.message_transport import MessagePipes
from common.message import run_worker
from common.logging_config import setup_logging

class JudgeWorker:
    def __init__(self, config_path: str):
        config = JSONFileManager.load_file(config_path) 

        self.response_scorer = ResponseScorer(
            config["urls"]["transcription_url"],
            config["urls"]["judge_url"],
            config["urls"].get("rating_rectifier_url", ""),
            config["device_manager_type"],
            config["judge_worker"]
        )

        self.message_service = MessagePipes(read_path = "/tmp/coordinator_to_judge_worker",
                            write_path = "/tmp/judge_worker_to_coordinator",
                            write_first = True) 
        self.wait_time = config["message_service"]["wait_time"]

        setup_logging(config["logger"]["logger_level"], os.path.join(config["paths"]["root_folder"], "judge_worker.log"))

    def judge(self, query_data: str):
        """Score one agent_tester result; returns (eval_id, payload) for the coordinator."""
        logging.info("----WORKING----")
        response, result_meta = self.response_scorer.get_judge_score(query_data)
        eval_id = result_meta["eval_id"]
        logging.info(f"----Completed analysis for {eval_id}----")
        return eval_id, response + "<meta_start>" + json.dumps(result_meta) + "<meta_end>"

    def client_server(self):
        run_worker(self.message_service, "judge_worker", self.wait_time, self.judge)

if __name__ == "__main__":
    config_path = "configs/config_template.json"
    if len(sys.argv) > 1:
       print(f"Config path set to {sys.argv[1]}")
       config_path = sys.argv[1]
    if os.environ.get("PIPELINE_TRACE"):
        from utils.trace_injection import install_tracing
        install_tracing(config_path)
    judge_worker = JudgeWorker(config_path)
    judge_worker.client_server()