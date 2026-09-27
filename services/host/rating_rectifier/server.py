"""
Rating Rectifier — backend (stateless).
======================================

The frontend owns all editing state in IndexedDB on the user's machine.
The server's only responsibilities are:

  1. Serve the static frontend (`/`, `/index.html`, `/static/*`).
  2. Accept rating corrections that the frontend pushes on download
     (POST /update_mistake_list).
  3. Return stored corrections on demand (POST /get_mistakes).

There is no per-session state, no uploaded-file storage, no row-by-row
edit API. Everything lives in the browser until the user explicitly
clicks Download, at which point the rectified JSONL is generated
client-side and only the rows whose *rating* changed are POSTed here.

Mistakes table — exactly 4 columns
----------------------------------
    id              TEXT PRIMARY KEY   -- generated server-side from
                                       --   timestamp (+ small uuid tail
                                       --   to disambiguate inserts that
                                       --   land in the same nanosecond)
    unique_id       TEXT NOT NULL      -- sha256 hash provided by the
                                       --   frontend; derived from
                                       --   image + gt_answer (and
                                       --   question if/when added back)
    judge_rating    TEXT NOT NULL      -- the rating before correction
    correct_rating  TEXT NOT NULL      -- the human-corrected rating
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
import uuid
from pathlib import Path
from typing import List

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Unique-id helper
# --------------------------------------------------------------------------- #
#
# Mirrors the JS implementation in static/app.js:
#
#     sha256( image_b64  +  US  +  question  +  US  +  gt_answer )
#
# where US is the ASCII unit-separator byte (0x1f). Strings are UTF-8
# encoded, matching the browser's TextEncoder. A client that wants to
# query /get_mistakes for a particular example can either compute this
# hash itself or POST to /compute_unique_id and use the returned value.

_US = "\x1f"

def compute_unique_id(image_b64: str, question: str, gt_answer: str) -> str:
    payload = (image_b64 or "") + _US + (question or "") + _US + (gt_answer or "")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

BASE_DIR   = Path(__file__).parent.resolve()
DATA_DIR   = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
DB_PATH    = DATA_DIR / "judge_error.db"
INDEX_FILE = STATIC_DIR / "index.html"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #

EXPECTED_COLUMNS = {
    "id", "unique_id",
    "judge_rating", "correct_rating",
    "device_type",
    "question", "gt_answer",
    "judge_response",
}


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the mistakes table; migrate away from any legacy schema."""
    with get_db() as conn:
        # If a legacy `mistakes` table from an older build is present
        # with a different column set, drop it so the new schema can be
        # created cleanly. This is destructive, but the v2 contract is
        # that mistakes survive only after Download → POST.
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mistakes'"
        ).fetchone()
        if row:
            existing = {r[1] for r in conn.execute("PRAGMA table_info(mistakes)").fetchall()}
            if existing != EXPECTED_COLUMNS:
                print(f"[migration] mistakes table had columns {sorted(existing)}; "
                      f"dropping and recreating to match {sorted(EXPECTED_COLUMNS)}.")
                conn.execute("DROP TABLE mistakes")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS mistakes (
                id              TEXT PRIMARY KEY,
                unique_id       TEXT NOT NULL,
                judge_rating    TEXT NOT NULL,
                correct_rating  TEXT NOT NULL,
                device_type     TEXT NOT NULL,
                question        TEXT NOT NULL,
                gt_answer       TEXT NOT NULL,
                judge_response  TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mistakes_unique_id ON mistakes(unique_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mistakes_device_type ON mistakes(device_type)"
        )

        # Clean up legacy session tables from v1 if they're still hanging around.
        for legacy in ("sessions", "session_rows"):
            if conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (legacy,),
            ).fetchone():
                conn.execute(f"DROP TABLE {legacy}")
                print(f"[migration] dropped legacy table: {legacy}")

        conn.commit()


init_db()


def _new_id() -> str:
    """ID derived from a high-resolution timestamp, with an 8-char uuid tail
    to guarantee uniqueness if two inserts share the same nanosecond."""
    return f"{time.time_ns()}_{uuid.uuid4().hex[:8]}"


# --------------------------------------------------------------------------- #
# FastAPI app
# --------------------------------------------------------------------------- #

app = FastAPI(title="Rating Rectifier", version="2.0.0")


@app.on_event("startup")
def _verify_static_assets() -> None:
    missing = [
        p.name
        for p in (INDEX_FILE, STATIC_DIR / "app.js", STATIC_DIR / "style.css")
        if not p.exists()
    ]
    if missing:
        raise RuntimeError(
            f"Static assets not found in {STATIC_DIR}: {missing}. "
            "Make sure the 'static' folder sits next to server.py."
        )


@app.get("/health")
def health() -> dict:
    """Health-check endpoint for the Rating Rectifier service."""
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(INDEX_FILE, media_type="text/html")


@app.get("/index.html", include_in_schema=False)
def root_index_html() -> FileResponse:
    return FileResponse(INDEX_FILE, media_type="text/html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    # 204 No Content must NOT have a response body. JSONResponse(content=None)
    # would emit b"null" and trip the ASGI server's Content-Length check.
    return Response(status_code=204)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

class Mistake(BaseModel):
    unique_id:      str
    judge_rating:   str   # str because callers may send ints or "3" etc.
    correct_rating: str
    device_type:    str
    question:       str
    gt_answer:      str
    judge_response: str


class MistakeListPayload(BaseModel):
    mistakes: List[Mistake]


class GetMistakesPayload(BaseModel):
    # All three are required — missing any field returns a 422 from
    # Pydantic with a per-field error message.
    unique_id:     str
    device_type:   str
    example_count: int = Field(..., gt=0, lt=5,
                               description="Strictly greater than 0 and less than 5.")


class ComputeUniqueIdPayload(BaseModel):
    image_b64: str
    question:  str
    gt_answer: str


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@app.post("/update_mistake_list")
def update_mistake_list(payload: MistakeListPayload) -> dict:
    """Persist a batch of mistakes pushed by the frontend on download."""
    inserted = 0
    skipped  = 0

    with get_db() as conn:
        for m in payload.mistakes:
            uid = m.unique_id.strip()
            dev = m.device_type.strip()
            # question / gt_answer / judge_response may legitimately be
            # empty strings; only unique_id and device_type gate insertion.
            if not uid or not dev:
                skipped += 1
                continue

            # Make sure id is unique even within a single ns bucket.
            mid = _new_id()
            while conn.execute("SELECT 1 FROM mistakes WHERE id = ?", (mid,)).fetchone():
                mid = _new_id()

            conn.execute(
                "INSERT INTO mistakes "
                "(id, unique_id, judge_rating, correct_rating, "
                " device_type, question, gt_answer, judge_response) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    mid, uid,
                    str(m.judge_rating), str(m.correct_rating),
                    dev,
                    str(m.question), str(m.gt_answer), str(m.judge_response),
                ),
            )
            inserted += 1

        conn.commit()

    return {"inserted": inserted, "skipped": skipped}


@app.post("/get_mistakes")
def get_mistakes(payload: GetMistakesPayload) -> dict:
    """
    Return up to `example_count` stored mistakes matching `unique_id`
    AND `device_type`. All three payload fields are required.

    `example_count` is bounded to 1..4 inclusive at the model level.
    Rows are returned newest first (`ORDER BY id DESC`).
    """
    sql = (
        "SELECT id, unique_id, judge_rating, correct_rating, "
        "device_type, question, gt_answer, judge_response "
        "FROM mistakes "
        "WHERE unique_id = ? AND device_type = ? "
        "ORDER BY id DESC LIMIT ?"
    )
    with get_db() as conn:
        rows = conn.execute(
            sql,
            (payload.unique_id, payload.device_type, payload.example_count),
        ).fetchall()
    
    if len(rows) < payload.example_count:
        sql = (
            "SELECT id, unique_id, judge_rating, correct_rating, "
            "device_type, question, gt_answer, judge_response "
            "FROM mistakes "
            "WHERE unique_id = ?"
            "ORDER BY id DESC LIMIT ?"
        )
        rows_extend = conn.execute(
            sql,
            (payload.unique_id, payload.example_count - len(rows)),
        ).fetchall()
        rows = rows + rows_extend

    return {"mistakes": [dict(r) for r in rows]}


@app.post("/compute_unique_id")
def compute_unique_id_endpoint(payload: ComputeUniqueIdPayload) -> dict:
    """
    Return the canonical unique_id for an example given its
    base64-encoded image, the question text, and the GT answer.

    Useful for clients that want to query /get_mistakes without
    implementing the SHA-256 hashing themselves. Matches the browser's
    computation bit-for-bit:

        sha256( image_b64 + 0x1f + question + 0x1f + gt_answer )

    All three fields are required.
    """
    uid = compute_unique_id(payload.image_b64, payload.question, payload.gt_answer)
    return {"unique_id": uid}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8282)
