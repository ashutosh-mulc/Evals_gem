import json, time, sys, os
import queue
import zmq
import threading
from copy import deepcopy
from tqdm import tqdm
import logging

from utils.file_utils import *
from utils.message_transport import MessagePipes
from common.message import *
from metric_coordinator.db_manager import DBManager

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

        #logger setup
        logging_config = config["logger"]
        
        logging_level = logging.DEBUG
        match(logging_config["logger_level"]):
            case "debug":
                logger_level = logging.DEBUG
            case "info":
                logger_level = logging.INFO
            case "warning":
                logger_level = logging.WARNING
            case "error":
                logger_level = logging.ERROR
            case "critical":
                logger_level = logging.CRITICAL
            case _:
                logger_level = logging.DEBUG
        logging.basicConfig(
            level = logging_level,
            filename = os.path.join(config["paths"]["root_folder"], "coordinator.log"),
            format = '%(asctime)s\t%(levelname)s\t%(module)s\t%(process)s\t%(thread)s\t%(message)s'
        )

        #setup message_service
        self.message_services = {
                            "judge_worker": MessagePipes(read_path = "/tmp/judge_worker_to_coordinator",
                                    write_path = "/tmp/coordinator_to_judge_worker",
                                    write_first = False),
                            "agent_tester": MessagePipes(read_path = "/tmp/agent_tester_to_coordinator",
                                    write_path = "/tmp/coordinator_to_agent_tester",
                                    write_first = False)
                            }

        self.message_queues = {
                            "tester_request": queue.Queue(),
                            "tester_response": queue.Queue(),
                            "judge_request": queue.Queue(),
                            "judge_response": queue.Queue()
                            }  
    
    def host_agent_tester_server(self):
        wait_response = Message(eval_id = '',
                                msg_type = "RESPONSE",
                                status = "WAIT",
                                payload = "",
                                sender = "coordinator",
                                )
        
        stop_service = False

        while not stop_service:
            try:            
                encoded_msg = self.message_services["agent_tester"].recv()
            except BrokenPipeError:
                print("ERROR: agent_tester client died! FIX IT! WAITING!"); logging.error("ERROR: agent_tester client died! FIX IT! WAITING!")
                self.message_services["agent_tester"].reinit_fd(write_first = True)
                continue

            msg = json.loads(encoded_msg.decode())

            last_msg_recieved = int(time.time())

            if msg["msg_type"] == "REQUEST":
                print("Received msg from agent_tester");logging.info("Received msg from agent_tester")

                current_process_status = msg["status"]
                match(current_process_status):
                    case "WORK":
                        self.message_queues["tester_request"].put(deepcopy(msg)) #producer
                        if self.message_queues["tester_request"].qsize() > 1:
                            raise NotImplementedError
                    case "READY":
                        self.message_queues["tester_request"].put(deepcopy(msg)) #producer
                        if self.message_queues["tester_request"].qsize() > 1:
                            raise NotImplementedError
                    case _:
                        pass
                
                response = wait_response
                try: 
                    response = self.message_queues["tester_response"].get_nowait() #consumer
                    print("----ASSIGNING TASK TO TESTER----"); logging.info("----ASSIGNING TASK TO TESTER----")
                except queue.Empty:
                    print("----ASKING TESTER TO WAIT----"); logging.info("----ASSIGNING TASK TO TESTER----")
                
                response.msg_id = msg["msg_id"]
                if response.status == "STOP":
                    print("----STOPPING AGENT TESTER----"); logging.info("----STOPPING AGENT TESTER----")
                    stop_service = True
                
                try:
                    self.message_services["agent_tester"].send(
                        payload = json.dumps(response.get_json()).encode()
                    )
                except BrokenPipeError:
                    print("ERROR: agent_tester client died! FIX IT!"); logging.error("ERROR: agent_tester client died! FIX IT!")
                    self.message_services["agent_tester"].reinit_fd(write_first = True)
                # print("Replied to agent_tester", json.dumps(response.get_json()))
            else:
                raise NotImplementedError
    
    def host_judge_worker_server(self):
        wait_response = Message(eval_id = '',
                                msg_type = "RESPONSE",
                                status = "WAIT",
                                payload = "",
                                sender = "coordinator",
                                )
        
        stop_service = False

        while not stop_service: 
            try:             
                # pass
                encoded_msg = self.message_services["judge_worker"].recv()
            except BrokenPipeError:
                print("ERROR: judge_worker client died! FIX IT! WAITING!"); logging.error("ERROR: judge_worker client died! FIX IT! WAITING!")
                self.message_services["judge_worker"].reinit_fd(write_first = True)
                continue
            

            msg = json.loads(encoded_msg.decode())

            last_msg_recieved = int(time.time())

            if msg["msg_type"] == "REQUEST":
                print("Received msg from judge_worker"); logging.info("Received msg from judge_worker")

                current_process_status = msg["status"]
                match(current_process_status):
                    case "WORK":
                        self.message_queues["judge_request"].put(deepcopy(msg)) #producer
                        if self.message_queues["judge_request"].qsize() > 1:
                            raise NotImplementedError
                    case "READY":
                        self.message_queues["judge_request"].put(deepcopy(msg)) #producer
                        if self.message_queues["judge_request"].qsize() > 1:
                            raise NotImplementedError
                    case _:
                        pass
                
                response = wait_response
                try: 
                    response = self.message_queues["judge_response"].get_nowait() #consumer
                    print("----ASSIGNING TASK TO JUDGE----"); logging.info("----ASSIGNING TASK TO JUDGE----"); 
                except queue.Empty:
                    print("----ASKING JUDGE TO WAIT----"); logging.info("----ASKING JUDGE TO WAIT----")
                
                response.msg_id = msg["msg_id"]
                if response.status == "STOP":
                    print("----STOPPING JUDGE WORKER----"); logging.info("----STOPPING JUDGE WORKER----")
                    stop_service = True
                
                try:
                    self.message_services["judge_worker"].send(
                        payload = json.dumps(response.get_json()).encode()
                    )
                except BrokenPipeError:
                    print("ERROR: judge_worker client died! FIX IT! WAITING!"); logging.error("----STOPPING JUDGE WORKER----")
                    self.message_services["judge_worker"].reinit_fd(write_first = True)
            else:
                raise NotImplementedError

    
    def main(self):
        agent_tester_server_thread = threading.Thread(target = self.host_agent_tester_server, daemon = True)
        agent_tester_server_thread.start()
        judge_worker_server_thread = threading.Thread(target = self.host_judge_worker_server, daemon = True)
        judge_worker_server_thread.start()

        work_msg = Message(eval_id = '',
                msg_type = "RESPONSE",
                status = "WORK",
                payload = json.dumps(self.question_dataset[self.start_idx]),
                sender = "coordinator")

        add_judge_task_when_available = False
        tc_excecuted = set(); tc_judged = set()
        current_tester_task = current_judge_task = None
        dataset_size = self.end_idx - self.start_idx + 1

        pbar = tqdm(total = dataset_size, desc = "Evaluating")
        while len(tc_excecuted) < dataset_size or len(tc_judged) < dataset_size:
            try:
                tester_request = self.message_queues["tester_request"].get_nowait() #consumer
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
                    self.message_queues["tester_response"].put(deepcopy(work_msg))
                    
                    self.qdata_idx += 1                
            except queue.Empty:
                pass
            
            try:
                judge_request = self.message_queues["judge_request"].get_nowait() #consumer
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
                    logging.debug("Assigning task inside loop")
                    next_task_id = min(list(self.judge_datadict.keys()))
                    add_judge_task_when_available = False

                    judge_qinfo = self.judge_datadict.pop(next_task_id)
                    current_judge_task = json.loads(judge_qinfo)
                    self.db_manager.update_task(next_task_id, "ASSIGNED", judge_qinfo)
                    work_msg.payload = judge_qinfo
                    self.message_queues["judge_response"].put(deepcopy(work_msg))
                else:
                    add_judge_task_when_available = True

            except queue.Empty:
                pass
            
            if self.judge_datadict and add_judge_task_when_available:
                logging.debug("Assigning task outside loop")
                next_task_id = min(list(self.judge_datadict.keys()))
                add_judge_task_when_available = False

                judge_qinfo = self.judge_datadict.pop(next_task_id)
                current_judge_task = json.loads(judge_qinfo)
                self.db_manager.update_task(next_task_id, "ASSIGNED", judge_qinfo)
                work_msg.payload = judge_qinfo
                self.message_queues["judge_response"].put(deepcopy(work_msg))

        stop_msg = Message(eval_id = '',
                        msg_type = "RESPONSE",
                        status = "STOP",
                        payload = "",
                        sender = "coordinator")
        self.message_queues["tester_response"].put(deepcopy(stop_msg))
        self.message_queues["judge_response"].put(deepcopy(stop_msg))
        agent_tester_server_thread.join() 
        judge_worker_server_thread.join() # if we forcefully kill the main process it should kill this thread otherwise wait until the thread closes gently
        
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