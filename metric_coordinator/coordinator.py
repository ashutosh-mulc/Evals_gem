import json, sys, os
import queue
import threading
from copy import deepcopy
from tqdm import tqdm
import logging

from utils.file_utils import JSONFileManager, JSONLFileManager
from utils.message_transport import MessagePipes
from common.message import Message
from common.logging_config import setup_logging
from metric_coordinator.db_manager import DBManager

CLIENTS = ("judge_worker", "agent_tester")  # FIFO open order matters: opens block until the peer connects


def _response(status: str, payload: str = "") -> Message:
    return Message(eval_id="", msg_type="RESPONSE", status=status, payload=payload, sender="coordinator")


class MetricCoordinator:
    def __init__(self, config_path):
        config = JSONFileManager.load_file(config_path)

        _, self.question_dataset = JSONLFileManager.load_file(config["paths"]["dataset_file"])
        self.start_idx = config["dataset_start_index"]; self.end_idx = min(config["dataset_end_index"], len(self.question_dataset) - 1)
        self.qdata_idx = self.start_idx
        self.judge_datadict = {}        

        #setup DBManager
        db_backup_folder = config["paths"]["queue_backup_folder"]
        queue_path = config["paths"]["queue_file"]
        self.db_manager = DBManager(db_backup_folder, queue_path)

        setup_logging(config["logger"]["logger_level"], os.path.join(config["paths"]["root_folder"], "coordinator.log"))

        # One FIFO pair per client; each client's server thread talks to main() through two queues:
        # requests (client → main) and responses (main → client).
        self.message_services = {
            name: MessagePipes(read_path=f"/tmp/{name}_to_coordinator",
                               write_path=f"/tmp/coordinator_to_{name}",
                               write_first=False)
            for name in CLIENTS
        }
        self.requests = {name: queue.Queue() for name in CLIENTS}
        self.responses = {name: queue.Queue() for name in CLIENTS}

    def _serve(self, name: str):
        """Answer every request from one client: queue it for main(), reply with the next response or WAIT."""
        pipes = self.message_services[name]
        wait_response = _response("WAIT")

        while True:
            try:
                msg = json.loads(pipes.recv().decode())
            except BrokenPipeError:
                logging.error(f"ERROR: {name} client died! FIX IT! WAITING!")
                pipes.reinit_fd(write_first=True)
                continue

            if msg["msg_type"] != "REQUEST":
                raise NotImplementedError
            logging.info(f"Received msg from {name}")

            if msg["status"] in ("WORK", "READY"):
                self.requests[name].put(deepcopy(msg))
                if self.requests[name].qsize() > 1:
                    raise NotImplementedError

            try:
                response = self.responses[name].get_nowait()
                logging.info(f"----ASSIGNING TASK TO {name}----")
            except queue.Empty:
                response = wait_response
                logging.info(f"----ASKING {name} TO WAIT----")

            response.msg_id = msg["msg_id"]
            try:
                pipes.send(payload=json.dumps(response.get_json()).encode())
            except BrokenPipeError:
                logging.error(f"ERROR: {name} client died! FIX IT!")
                pipes.reinit_fd(write_first=True)

            if response.status == "STOP":
                logging.info(f"----STOPPING {name}----")
                return

    def _assign_next_judge_task(self, work_msg: Message) -> dict:
        """Hand the lowest pending eval_id to the judge; return it as the current judge task."""
        next_task_id = min(self.judge_datadict)
        judge_qinfo = self.judge_datadict.pop(next_task_id)
        self.db_manager.update_task(next_task_id, "ASSIGNED", judge_qinfo)
        work_msg.payload = judge_qinfo
        self.responses["judge_worker"].put(deepcopy(work_msg))
        return json.loads(judge_qinfo)

    def main(self):
        server_threads = [threading.Thread(target=self._serve, args=(name,), daemon=True) for name in CLIENTS]
        for t in server_threads:
            t.start()

        work_msg = _response("WORK")

        add_judge_task_when_available = False
        tc_excecuted = set(); tc_judged = set()
        current_tester_task = current_judge_task = None
        dataset_size = self.end_idx - self.start_idx + 1

        pbar = tqdm(total = dataset_size, desc = "Evaluating")
        while len(tc_excecuted) < dataset_size or len(tc_judged) < dataset_size:
            try:
                tester_request = self.requests["agent_tester"].get_nowait()
                #TODO: semi-automate logic for waiting and re-evaluating tc can be added here
                if tester_request["status"] == "WORK":
                    if current_tester_task and current_tester_task["eval_id"] != tester_request["eval_id"]: # verify the completed task otherwise reassign it
                        self.qdata_idx -= 1 
                    else:
                        self.db_manager.add_task(tester_request["payload"])
                        self.judge_datadict[tester_request["eval_id"]] = tester_request["payload"]
                        tc_excecuted.add(tester_request["eval_id"])

                elif tester_request["status"] == "READY":
                    if current_tester_task: #if task was assigned earlier start from there
                        self.qdata_idx -= 1
                else:
                    raise NotImplementedError

                if self.qdata_idx <= self.end_idx:
                    q_info = self.question_dataset[self.qdata_idx]
                    current_tester_task = q_info
                    work_msg.payload = json.dumps(q_info)
                    self.responses["agent_tester"].put(deepcopy(work_msg))
                    
                    self.qdata_idx += 1                
            except queue.Empty:
                pass
            
            try:
                judge_request = self.requests["judge_worker"].get_nowait()
                #TODO: semi-automated live update of judge request can be added here
                if judge_request["status"] == "WORK":
                    if current_judge_task and current_judge_task["eval_id"] == judge_request["eval_id"]: # verify the completed and only then pop it
                        self.db_manager.update_task(judge_request["eval_id"], "COMPLETED", judge_request["payload"])
                        
                        pbar.update(1 - int(judge_request["eval_id"] in tc_judged))
                        
                        tc_judged.add(judge_request["eval_id"])
                    else:
                        self.judge_datadict[current_judge_task["eval_id"]] = json.dumps(current_judge_task)
                elif judge_request["status"] == "READY":
                    if current_judge_task:
                        self.judge_datadict[current_judge_task["eval_id"]] = json.dumps(current_judge_task)
                else:
                    raise NotImplementedError

                if self.judge_datadict:
                    current_judge_task = self._assign_next_judge_task(work_msg)
                    add_judge_task_when_available = False
                else:
                    add_judge_task_when_available = True

            except queue.Empty:
                pass
            
            if self.judge_datadict and add_judge_task_when_available:
                current_judge_task = self._assign_next_judge_task(work_msg)
                add_judge_task_when_available = False

        for name in CLIENTS:
            self.responses[name].put(_response("STOP"))
        for t in server_threads:
            t.join()  # daemon threads: killing the main process still ends them
        
        pbar.close()

# --------- Entry Point ---------

if __name__ == "__main__":
    config_path = "configs/config_template.json"
    if len(sys.argv) > 1:
       print(f"Config path set to {sys.argv[1]}")
       config_path = sys.argv[1]
    if os.environ.get("PIPELINE_TRACE"):
        from utils.trace_injection import install_tracing
        install_tracing(config_path)
    coordinator = MetricCoordinator(config_path)
    coordinator.main()