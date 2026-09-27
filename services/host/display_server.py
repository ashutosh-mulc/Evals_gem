from flask import Flask, jsonify
from threading import Lock
class DisplayServer:
    def __init__(self):
        self.app = Flask(__name__)
        self._setup_routes()
        self.image_status_relayed = False
        
        self.image_status = {
            "action": "stop", 
            "image_data": None
        }
        self.image_status_lock = Lock()
    
    def _setup_routes(self,):
        @self.app.route("/get_image", methods = ["GET"])
        def get_image():
            self.image_status_relayed = True
            with self.image_status_lock:
                image_status = self.image_status
            return jsonify(image_status), 200
    
    def set_image_status(self, image: str, action: str):
        with self.image_status_lock:
            self.image_status["action"] = action
            self.image_status["image_data"] = image

        self.image_status_relayed = False
        while True:
            if self.image_status_relayed:
                break
    
    def get_app(self):
        return self.app
