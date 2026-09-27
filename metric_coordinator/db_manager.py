import time, os, shutil, os, json
from threading import Lock
import sqlite3

class DBManager:
    def __init__(self, backup_folder, db_path):
        # Create backup folder if it doesn't exist
        os.makedirs(backup_folder, exist_ok=True)
        
        if os.path.exists(db_path):
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_folder, f"queue_{timestamp}.db")
            shutil.copy2(db_path, backup_path)  # Make a backup
            
            # Wipe existing DB
            self._wipe_db(db_path)

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = Lock()
        self._create_table()

    def _create_table(self):
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metric_queue (
                    id TEXT PRIMARY KEY,
                    question TEXT,
                    eval_json TEXT,
                    status TEXT,
                    result_json TEXT,
                    created_at INTEGER
                )
            """
            )
        print("New metric_queue table created!")
    
    def _wipe_db(self, db_path):
        """Delete all tables from the database file."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        for (table_name,) in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            print(f"Dropped table {table_name}")

        conn.commit()
        cursor.execute("VACUUM;")  # Clean up unused space
        print("Database vacuumed and size reduced.")
        conn.close()

    def add_task(self, json_payload : str) -> None:
        json_payload = json.loads(json_payload)
        eval_id = json_payload["eval_id"]
        question = json_payload["question"]
        created_at = int(time.time())
        with self.lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO metric_queue (id, question, eval_json, status, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    eval_id,
                    question,
                    json.dumps(json_payload),
                    "PENDING",
                    "",
                    created_at,
                ),
            )
            self.conn.commit()
        return eval_id

    def update_task(self, eval_id: str, status: str, result_json: str = ""):
        with self.lock:
            self.conn.execute(
                """
                UPDATE metric_queue SET status = ?, result_json = ? WHERE id = ?
                """,
                (status, result_json, eval_id),
            )
            self.conn.commit()