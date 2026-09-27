import zmq, json, time, sys, os
import threading, warnings
import logging

from judge_worker.response_scorer import ResponseScorer
from utils.file_utils import *
from utils.message_transport import MessagePipes
from common.message import *
from common.logging_config import setup_logging

class JudgeWorker:
    def __init__(self, config_path: str):
        # load config
        config = JSONFileManager.load_file(config_path) 

        #setup response scorer
        self.response_scorer = ResponseScorer(
            config["urls"]["transcription_url"],
            config["urls"]["judge_url"],
            config["urls"].get("rating_rectifier_url", ""),
            config["device_manager_type"],
            config["judge_worker"]
        )

        #setup message service
        self.message_service = MessagePipes(read_path = "/tmp/coordinator_to_judge_worker",
                            write_path = "/tmp/judge_worker_to_coordinator",
                            write_first = True) 
        self.message_service_config = { 
                                    "wait_time": config["message_service"]["wait_time"]
                                    }
        
        setup_logging(config["logger"]["logger_level"], os.path.join(config["paths"]["root_folder"], "judge_worker.log"))

    def send_message(self, eval_id: str, payload: str, current_status: str):
        msg = Message(
            eval_id = eval_id,
            msg_type = "REQUEST",
            status = current_status,
            payload = payload,
            sender = "judge_worker"
        )

        msg_bytes = json.dumps(msg.get_json()).encode()
        logging.debug(f"Sent Request: {msg_bytes.decode()}")
        response_bytes = self.message_service.request(payload = msg_bytes, timeout = 10)
        logging.debug(f"Received response: {response_bytes.decode()}")
        
        response = json.loads(response_bytes.decode())
        Message.check_response(msg.msg_id, "coordinator", response)

        return response["payload"], response["status"]  
        
    def client_server(self):
        current_status = "READY"; query_data = ""
        stop_process = False
        while not stop_process:
            payload = ""; eval_id = ""
            match(current_status):
                case "READY":
                    logging.info("Judge worker is ready!")

                case "WAIT":
                    time.sleep(self.message_service_config["wait_time"])

                case "WORK":
                    logging.info("----WORKING----")
                    response, result_meta = self.response_scorer.get_judge_score(query_data)
                    eval_id = result_meta["eval_id"]
                    payload = response + "<meta_start>" + json.dumps(result_meta) + "<meta_end>"
                    logging.info(f"----Completed analysis for {eval_id}----")

                case "STOP":
                    stop_process = False
                    break

                case _:
                    raise NotImplementedError
                
            query_data, current_status = self.send_message(eval_id, payload, current_status)

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