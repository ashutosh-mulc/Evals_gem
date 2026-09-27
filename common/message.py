import json
import logging
import time
import uuid

message_type = [
    "REQUEST",
    "RESPONSE"
]

process_status = [
    "READY",
    "WAIT",
    "WORK",
    "STOP"
]

class Message:
    def __init__(self, eval_id: str, msg_type: str, status: str, payload: str, sender: str):
        assert msg_type in message_type, "Unknown message_type type!"
        assert status in process_status, "Unknown process_status type!"
        assert len(eval_id) in [0, 6], "Invalid eval_id format!"
        assert sender in ("agent_tester", "coordinator", "judge_worker"), "Unknown sender!"

        self.msg_id =  str(uuid.uuid4())
        self.eval_id = eval_id
        self.msg_type = msg_type
        self.status = status
        self.payload = payload
        self.sender = sender
    
    def get_json(self,):
        return {
            "msg_id": self.msg_id,
            "eval_id": self.eval_id,
            "msg_type": self.msg_type,
            "status": self.status,
            "payload": self.payload,
            "sender": self.sender
        }

    @staticmethod
    def check_response(msg_id: str, sender: str, response: dict):
        assert response["msg_type"] == "RESPONSE", "Bad msg_type!"
        assert response["msg_id"] == msg_id, "Bad msg_id!"
        assert response["sender"] == sender, "Bad sender!"


def run_worker(pipes, sender: str, wait_time: float, do_work) -> None:
    """Client side of the coordinator protocol (agent_tester, judge_worker).

    Each request carries our current status; the coordinator's reply sets the next one:
    READY (first request), WAIT → sleep, WORK → ``do_work(payload)`` returns
    (eval_id, result_payload) to send back, STOP → return.
    """
    status, data = "READY", ""
    while True:
        eval_id, payload = "", ""
        if status == "READY":
            logging.info(f"{sender} is ready!")
        elif status == "WAIT":
            time.sleep(wait_time)
        elif status == "WORK":
            eval_id, payload = do_work(data)
        elif status == "STOP":
            return
        else:
            raise NotImplementedError(status)

        msg = Message(eval_id=eval_id, msg_type="REQUEST", status=status, payload=payload, sender=sender)
        msg_bytes = json.dumps(msg.get_json()).encode()
        logging.debug(f"Sent request: {msg_bytes}")
        response_bytes = pipes.request(payload=msg_bytes, timeout=10)
        logging.debug(f"Received response: {response_bytes}")

        response = json.loads(response_bytes.decode())
        Message.check_response(msg.msg_id, "coordinator", response)
        status, data = response["status"], response["payload"]
