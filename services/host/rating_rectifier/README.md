# Rating Rectifier — v2

A small web tool for going through a JSONL of model-judged ratings and
correcting the ones that are wrong. The rectified JSONL is downloaded
back to the user; only the rows whose **rating** changed are pushed to a
local mistakes database on the server.

---

## What's new in v2

v2 is a substantial rework of the data flow. **The server is now stateless
except for the mistakes table.** Everything else — the parsed file, the
tag mapping, the per-iteration edits — lives in the browser's IndexedDB.

| | v1 | **v2** |
|---|---|---|
| File upload | POSTs to server; server stores rows in SQLite | Parsed in the browser, written to IndexedDB |
| Tag mapping & editable fields | POSTed to server, stored per-session | Stored in IndexedDB |
| Row navigation | Fetch from server, save edits per row | Pure IndexedDB reads/writes; zero network traffic |
| Mistakes table | 7 columns including `device_type`, `question`, `transcribed_answer` | **Exactly 4 columns** |
| Device-type modal | Required before download | Removed |
| Question Audio tag | Required | **Commented out / removed** |

Nothing reaches the server until you click **Download**, at which point:

1. The rectified JSONL is rebuilt in the browser and saved as a file.
2. Only iterations whose **rating** actually changed are POSTed to
   `/update_mistake_list`.

---

## Mistakes table — 8 columns

```sql
CREATE TABLE mistakes (
    id              TEXT PRIMARY KEY,    -- server-generated from time.time_ns() + uuid tail
    unique_id       TEXT NOT NULL,       -- sha256(image_b64 + 0x1f + question + 0x1f + gt_answer)
    judge_rating    TEXT NOT NULL,       -- the rating that was being corrected
    correct_rating  TEXT NOT NULL,       -- the human-supplied correction
    device_type     TEXT NOT NULL,       -- which device produced the original judgement
    question        TEXT NOT NULL,       -- the question being asked about the image
    gt_answer       TEXT NOT NULL,       -- ground-truth answer the judge was scoring against
    judge_response  TEXT NOT NULL        -- the transcribed answer the judge graded
);
CREATE INDEX idx_mistakes_unique_id   ON mistakes(unique_id);
CREATE INDEX idx_mistakes_device_type ON mistakes(device_type);
```

`device_type` is collected from a modal that appears when the user clicks
**Download** — they pick one of the predefined device types
(`jinju-gemini`, `s25-gemini-live`, `s25-gemini-upload`, `s25-gpt-live`,
`meta-live`, `s25-claude-live`), and the same label is stamped onto
every rating correction in that batch.

`question` and `gt_answer` are the **original** values from the source
JSONL — they identify *what was being judged*, independent of any text
edits the user might make to the GT field. (Editing the GT in the
viewer changes what's written to the rectified JSONL on download; the
mistakes table still stores the original GT so the correction can be
traced back to the exact example.)

On startup the server **auto-migrates**: if it finds an old `mistakes`
table with a different column set (or the legacy `sessions` /
`session_rows` tables from v1), it drops them and creates the v2 schema.
A line is printed to stdout so you can see it happen. If you'd rather
start fresh, just delete `data/app.db`.

---

## `unique_id` hash

```
unique_id = sha256( image_b64  +  US  +  question  +  US  +  gt_answer )

where US = "\x1f" (ASCII unit-separator)
```

- The **original** image, question, and gt are used — not any edited
  values — so the same example always hashes to the same id even if
  the user edited the GT text in the viewer.
- The hash is computed **in the browser** using the Web Crypto API.
- **Plain HTTP / non-localhost contexts**: `crypto.subtle` is only
  available in secure contexts (HTTPS or localhost). If you host this
  on one machine and visit it from another over HTTP, the browser will
  hide `crypto.subtle`. v2 ships with a pure-JS SHA-256 fallback that
  kicks in automatically — verified bit-for-bit against Node's
  `crypto.createHash('sha256')` across the standard padding edge cases.

---

## API

The server exposes only what's needed for static delivery and mistake
storage:

| Method | Path | Purpose |
|---|---|---|
| GET | `/` and `/index.html` | The frontend |
| GET | `/static/*` | Static assets |
| GET | `/favicon.ico` | Empty 204 response (no body) |
| POST | `/update_mistake_list` | Insert corrections |
| POST | `/get_mistakes` | Query corrections (all fields required) |
| POST | `/compute_unique_id` | Compute the canonical unique_id for an example |

### POST `/update_mistake_list`

```jsonc
// Request — all seven mistake fields required
{
  "mistakes": [
    {
      "unique_id":      "<sha256 of image + question + gt>",
      "judge_rating":   "3",
      "correct_rating": "5",
      "device_type":    "jinju-gemini",
      "question":       "What is shown in the image?",
      "gt_answer":      "A red apple sits on the table.",
      "judge_response": "There's an apple on the desk."
    },
    ...
  ]
}

// Response
{ "inserted": 7, "skipped": 1 }   // skipped = entries with blank unique_id or device_type
```

The server generates each row's `id` from `time.time_ns()` plus a short
uuid tail (so simultaneous inserts can't collide on the primary key).
`question`, `gt_answer`, and `judge_response` may be empty strings —
only `unique_id` and `device_type` gate insertion.

### POST `/get_mistakes`

All three payload fields are **required**; missing any one returns a
422 with a per-field error message.

```jsonc
// Request
{
  "unique_id":     "<sha256>",
  "device_type":   "jinju-gemini",
  "example_count": 3                 // bounded: 1 ≤ n ≤ 4
}

// Response
{
  "mistakes": [
    {
      "id":             "1731701234123456789_a1b2c3d4",
      "unique_id":      "...",
      "judge_rating":   "3",
      "correct_rating": "5",
      "device_type":    "jinju-gemini",
      "question":       "...",
      "gt_answer":      "...",
      "judge_response": "..."
    }
  ]
}
```

Rows are ordered newest first (`ORDER BY id DESC`). Filtering is
`unique_id = ? AND device_type = ?` — both must match.

### POST `/compute_unique_id`

Companion endpoint so a caller of `/get_mistakes` can derive the
canonical unique_id for an example without re-implementing SHA-256.
The result is bit-for-bit identical to what the browser computes when
pushing a correction.

```jsonc
// Request — all three fields required
{
  "image_b64": "<base64 image string from the source JSONL>",
  "question":  "What is shown in the image?",
  "gt_answer": "A red apple sits on the table."
}

// Response
{
  "unique_id": "16461e4a01f7b1ccaa1e44235171b7d3bae2d351f961118d3d9527249d6e67e4"
}
```

The hash is `sha256(image_b64 + 0x1f + question + 0x1f + gt_answer)`,
with the strings UTF-8 encoded and concatenated using the ASCII
unit-separator byte. The same `compute_unique_id()` helper is exposed
at module scope in `server.py` for in-process callers.

---

## Navigation in the viewer

The image and question stay pinned at the top; below them, the
iterations form a horizontal **scroll-snap carousel** with one card
visible at a time. Position is shown by a dots pill above the carousel,
and the row counter in the top bar reads `Row 03 / 12 · Iter 02 / 03`
when there's more than one iteration.

| Action | Behavior |
|---|---|
| `→` or right edge nav | Next iteration. At the last iteration of a row, jumps to the next row's first iteration. |
| `←` or left edge nav | Previous iteration. At the first iteration of a row, jumps to the previous row's last iteration. |
| Click any dot | Jump straight to that iteration in the current row. |

Pending edits are flushed to IndexedDB on every navigation step (whether
within-row or cross-row), so a stray refresh won't lose work.

---

## Browser-side storage

IndexedDB database `rating-rectifier-db`, three object stores:

| Store | Key | Holds |
|---|---|---|
| `meta` | string | session metadata (filename, header, tag mapping, editable fields, rating-option universe) |
| `rows` | `row_index` | the original raw row from the JSONL (dict for dict-row files, list of dicts for list-row files) |
| `edits` | `"{rowIdx}-{iterIdx}"` | per-iteration override fields — `gt_answer`, `transcribed_answer`, `rating`, `reason` (only fields that actually differ from the original are stored) |

Loading a new file calls `clearAll()` on all three stores, so there is
never any cross-session contamination.

---

## Tags

```
Image, Question ID, Question, Response Audio, GT Answer, Transcribed Answer,
Rating, Reason, Iteration, Manually Verified
```

**Per-example** (shared across iterations of one row, read from the
first iteration of list rows): `Image`, `Question ID`, `Question`.
`Question ID` is rendered as a small badge at the top-left of the
viewer; `Image` and `Question` follow below it.

**Per-iteration** (one card per iteration): `Response Audio`,
`GT Answer`, `Transcribed Answer`, `Rating`, `Reason`,
`Manually Verified`.

**Identifier**: `Iteration` is required for **list-of-dicts** rows and
optional for **dict** rows.

**Optional tags**: `Question ID` and `Manually Verified`. If unmapped,
the viewer skips the badge / the column defaults to false.

Editable tags (the ones you can tick on stage 3): **GT Answer,
Transcribed Answer, Rating, Reason**.

### Per-iteration toggles

**Tell Judge** — appears at the right end of the **Rating** heading
whenever the user has changed the rating away from its original. Default
state when first shown:

| `|new − old|` | default |
|---|---|
| > 1 | **on** |
| ≤ 1 (incl. non-numeric) | **off** |

The user can toggle it manually after that. On Download, only iterations
whose final rating differs from the judge's *and* whose Tell Judge is on
are pushed to `/update_mistake_list`. Switching the rating back to its
original drops the toggle entirely.

**Manually Verified** — read-only indicator at the right end of each
iteration card header (same vertical line as the "Iteration N" title).
The displayed value is `original-was-true OR any-editable-field-differs`,
so the moment the user edits any of GT Answer / Transcribed Answer /
Rating / Reason, this pill flips on. The new value is written back to
the source field in the rectified JSONL.

### Iteration ordering and download truncation

Iteration cards in the viewer carousel are sorted by their **iteration
number** (numeric when possible, lexicographic otherwise), regardless of
their order in the source file.

On Download, list-of-dicts rows go through one more pass: as soon as an
iteration's **final** rating is greater than 2, every iteration after
it is dropped from the rectified JSONL. The user sees a notification:

```
Removed iteration 2 of question id q00001
Removed iteration 3 of question id q00001
```

If the row's `Question ID` tag isn't mapped, the notification falls
back to `Removed iteration N of question id row M`.

---

## Run it

```bash
pip install -r requirements.txt
python make_sample.py        # writes sample_dict_rows.jsonl and sample_list_rows.jsonl
python server.py             # binds 0.0.0.0:8000
```

Then open `http://<host>:8000` in your browser.

The first time you visit, the data layer initializes IndexedDB stores in
the browser. If you previously visited a v1 build of the page, do a
**hard refresh** (Ctrl+Shift+R / Cmd+Shift+R) so the browser picks up
the new `app.js`.

---

## File layout

```
rating_rectifier/
├── server.py                 stateless backend (~230 lines)
├── make_sample.py            generates the two sample JSONL files
├── requirements.txt
├── README.md                 (this file)
├── data/
│   └── app.db                created on first run
├── static/
│   ├── index.html
│   ├── app.js                IndexedDB-backed frontend (~700 lines)
│   └── style.css
└── sample_dict_rows.jsonl    (output of make_sample.py)
    sample_list_rows.jsonl
```
