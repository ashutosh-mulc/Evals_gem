import uuid
from enum import Enum, auto

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
