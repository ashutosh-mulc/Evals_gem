import json, base64, os

class JSONLFileManager:
    @staticmethod
    def load_file(path: str) -> (dict, list):
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        
        print(f"Loading JSONL {path.split('/')[-1]}...")
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        header = json.loads(lines[0])
        samples = [json.loads(line) for line in lines[1:]]
        return header, samples
    
    @staticmethod
    def dump_file(header: dict, data: list, path: str) -> None:
        with open(path, "w") as file:
            file.write(json.dumps(header) + "\n")
            for d in data:
                file.write(json.dumps(d) + "\n")

class JSONFileManager:
    @staticmethod
    def load_file(path: str) -> dict:
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        
        print(f"Loading JSON {path.split('/')[-1]}...")
        with open(path, "r") as file:
            json_data = json.load(file)
        return json_data
    
    @staticmethod
    def dump_file(data: dict, path: str, ) -> (dict, list):
        with open(path, "w") as file:
            json.dump(data, file, indent = 4)

class Base64Converter:
    @staticmethod
    def encode_to_base64(path: str) -> str:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path}")

        print(f"Encoding file {path.split('/')[-1]}...")
        with open(path, "rb") as f:
            file_bytes = f.read()

        file_base64 = base64.b64encode(file_bytes).decode("utf-8")
        payload = {
            "file_base64": file_base64,
            "metadata": {
                "filename": os.path.basename(path),
                "format": path.split('.')[-1],
                "size_bytes": len(file_base64),
            },
        }
        return payload
    
    @staticmethod
    def decode_to_file(base64_data: str, path: str) -> None:
        file_bytes = base64.b64decode(base64_data)
        
        print(f"Decoding encoded data to {path.split('/')[-1]}...")
        with open(path, "wb") as f:
            f.write(file_bytes)

        print(f"File saved to: {path}")
