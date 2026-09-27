#!/usr/bin/env python3
"""
Live Evaluation Dashboard — visualizes intermediate evaluation results
from the SQLite queue database while the evaluation pipeline is running.

Usage:
    python -m services.client.eval_dashboard --db metric_coordinator/queue.db
    python -m services.client.eval_dashboard --db metric_coordinator/queue.db --port 5055

Then open http://localhost:5055 in a browser.

Config (in eval_config.json):
    "dashboard": {
        "enabled": true,
        "port": 5055
    }
"""

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Add project root to sys.path so judge_worker can be imported
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, Response, jsonify, render_template_string, request


app = Flask(__name__)

# ── Globals set from CLI ────────────────────────────────────────────
DB_PATH = "metric_coordinator/queue.db"
RESULTS_ROOT = "data/results"


# ── Database helpers ────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def parse_result(row):
    """Parse the result_json field into structured data.

    Uses the robust parse_judge_response() from judge_worker.judge_response_parser
    to handle all judge response formats (JSON, markdown-fenced JSON, Python dict
    reprs, plain text, etc.).
    """
    from judge_worker.judge_response_parser import parse_judge_response

    raw = row["result_json"] or ""
    meta = {}
    analysis_text = ""
    rating = None
    # Extract <meta_start>{...}<meta_end>
    ms = raw.find("<meta_start>")
    me = raw.find("<meta_end>")
    if ms != -1 and me != -1:
        meta_json = raw[ms + len("<meta_start>"): me].strip()
        try:
            meta = json.loads(meta_json)
        except Exception:
            pass
        analysis_text = raw[:ms].strip()
    else:
        analysis_text = raw.strip()

    # Use the robust parser to extract rating and analysis
    analysis, parsed_rating = parse_judge_response(analysis_text)
    if parsed_rating is not None:
        rating = parsed_rating
    if analysis is not None:
        analysis_text = analysis

    # Fallback: check meta for rating
    if rating is None and meta:
        rating = meta.get("rating")

    return {"analysis": analysis_text, "rating": rating, "meta": meta, "raw": raw}



def parse_eval(row):
    """Parse the eval_json field."""
    try:
        return json.loads(row["eval_json"])
    except Exception:
        return {}


def get_all_rows():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM metric_queue ORDER BY created_at")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_row(eval_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM metric_queue WHERE id = ?", (eval_id,))
    r = cur.fetchone()
    conn.close()
    return dict(r) if r else None


# ── Summary helpers ────────────────────────────────────────────────

def compute_summary(rows):
    total = len(rows)
    status_counts = Counter(r["status"] for r in rows)
    completed = [r for r in rows if r["status"] == "COMPLETED"]
    pass_count = 0
    fail_count = 0
    unrated = 0
    by_type = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0, "unrated": 0})
    for r in completed:
        pr = parse_result(r)
        rating = pr["rating"]
        qt = pr["meta"].get("question_type", "unknown")
        by_type[qt]["total"] += 1
        if rating is None:
            unrated += 1
            by_type[qt]["unrated"] += 1
        elif int(rating) >= 3:
            pass_count += 1
            by_type[qt]["pass"] += 1
        else:
            fail_count += 1
            by_type[qt]["fail"] += 1
    return {
        "total": total,
        "status_counts": dict(status_counts),
        "completed": len(completed),
        "pass": pass_count,
        "fail": fail_count,
        "unrated": unrated,
        "by_type": {k: dict(v) for k, v in sorted(by_type.items())},
    }


# ── Routes ─────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    rows = get_all_rows()
    summary = compute_summary(rows)
    # Pre-parse each row for display
    display_rows = []
    for r in rows:
        pr = parse_result(r)
        display_rows.append({
            "id": r["id"],
            "question": r["question"],
            "status": r["status"],
            "rating": pr["rating"],
            "question_type": pr["meta"].get("question_type", ""),
            "judge_method": pr["meta"].get("judge_method", ""),
            "response_time": pr["meta"].get("response_time", ""),
            "answer": pr["meta"].get("answer", ""),
            "analysis": pr["analysis"],
        })

    return render_template_string(DASHBOARD_HTML, summary=summary, rows=display_rows)



@app.route("/api/summary")
def api_summary():
    rows = get_all_rows()
    return jsonify(compute_summary(rows))


@app.route("/api/rows")
def api_rows():
    rows = get_all_rows()
    # Strip large base64 fields
    slim = []
    for r in rows:
        d = {k: v for k, v in r.items() if k not in ("eval_json", "result_json")}
        pr = parse_result(r)
        d["rating"] = pr["rating"]
        d["question_type"] = pr["meta"].get("question_type", "")
        d["answer"] = pr["meta"].get("answer", "")
        d["judge_method"] = pr["meta"].get("judge_method", "")
        d["response_time"] = pr["meta"].get("response_time", "")
        d["analysis"] = pr["analysis"]
        slim.append(d)

    return jsonify(slim)


@app.route("/detail/<eval_id>")
def detail(eval_id):
    row = get_row(eval_id)
    if not row:
        return "Not found", 404
    eval_data = parse_eval(row)
    result = parse_result(row)
    # Find asset paths
    meta = eval_data.get("metadata", {})
    assets_dir = None
    if meta:
        img_path = meta.get("image_path", "")
        if img_path:
            assets_dir = str(Path(img_path).parent)
    # Read judge prompt if available
    judge_prompt = ""
    judge_prompt_path = result["meta"].get("judge_prompt_path", "")
    if judge_prompt_path and os.path.isfile(judge_prompt_path):
        try:
            with open(judge_prompt_path, "r", encoding="utf-8") as f:
                judge_prompt = f.read()
        except Exception:
            judge_prompt = "(Failed to read prompt file)"
    elif judge_prompt_path:
        judge_prompt = f"(Prompt file not found: {judge_prompt_path})"

    return render_template_string(
        DETAIL_HTML,
        row=row,
        eval_data=eval_data,
        result=result,
        meta=meta,
        assets_dir=assets_dir,
        judge_prompt=judge_prompt,
    )



@app.route("/asset")
def serve_asset():
    """Serve an asset file (image, audio, etc.) from the results directory."""
    fpath = request.args.get("path", "")
    if not fpath or not os.path.isfile(fpath):
        return "Not found", 404
    # Security: only allow files under RESULTS_ROOT
    abs_path = os.path.abspath(fpath)
    abs_root = os.path.abspath(RESULTS_ROOT)
    if not abs_path.startswith(abs_root):
        return "Forbidden", 403
    ext = Path(fpath).suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".txt": "text/plain",
        ".json": "application/json",
    }.get(ext, "application/octet-stream")
    with open(fpath, "rb") as f:
        data = f.read()
    return Response(data, mimetype=mime)


# ── HTML Templates ─────────────────────────────────────────────────

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="15">
<title>Eval Dashboard</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #f5f6fa; color: #2d3436; }
  h1 { color: #2d3436; margin-bottom: 5px; }
  .subtitle { color: #636e72; font-size: 14px; margin-bottom: 20px; }
  .cards { display: flex; gap: 15px; margin-bottom: 25px; flex-wrap: wrap; }
  .card { background: #fff; border-radius: 10px; padding: 18px 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); min-width: 120px; text-align: center; }
  .card .num { font-size: 32px; font-weight: bold; }
  .card .label { font-size: 13px; color: #636e72; margin-top: 4px; }
  .card.total .num { color: #0984e3; }
  .card.completed .num { color: #00b894; }
  .card.pass .num { color: #00b894; }
  .card.fail .num { color: #d63031; }
  .card.pending .num { color: #fdcb6e; }
  .card.unrated .num { color: #636e72; }
  .progress-bar { background: #dfe6e9; border-radius: 8px; height: 24px; margin: 10px 0 25px; overflow: hidden; }
  .progress-fill { background: #00b894; height: 100%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 12px; font-weight: bold; transition: width 0.5s; }
  table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
  th { background: #2d3436; color: #fff; padding: 10px 12px; text-align: left; font-size: 13px; }
  td { padding: 8px 12px; border-bottom: 1px solid #dfe6e9; font-size: 13px; }
  tr:hover { background: #f1f2f6; }
  .rating { display: inline-block; width: 28px; height: 28px; line-height: 28px; text-align: center; border-radius: 50%; font-weight: bold; font-size: 13px; }
  .rating.pass { background: #00b894; color: #fff; }
  .rating.fail { background: #d63031; color: #fff; }
  .rating.none { background: #dfe6e9; color: #636e72; }
  .status-badge { padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; }
  .status-COMPLETED { background: #00b894; color: #fff; }
  .status-ASSIGNED { background: #fdcb6e; color: #2d3436; }
  .status-PENDING { background: #dfe6e9; color: #636e72; }
  a { color: #0984e3; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .by-type { margin-top: 20px; }
  .by-type table { font-size: 13px; }
  .auto-refresh { font-size: 12px; color: #636e72; }
  .rating-clickable { cursor: pointer; transition: transform 0.15s; }
  .rating-clickable:hover { transform: scale(1.2); }
  .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; justify-content: center; align-items: center; }
  .modal-overlay.active { display: flex; }
  .modal-box { background: #fff; border-radius: 12px; padding: 25px; max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
  .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 2px solid #dfe6e9; padding-bottom: 10px; }
  .modal-title { font-size: 18px; font-weight: bold; }
  .modal-close { background: #d63031; color: #fff; border: none; border-radius: 50%; width: 30px; height: 30px; font-size: 16px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
  .modal-close:hover { background: #c0392b; }
  .modal-body { font-size: 14px; line-height: 1.6; color: #2d3436; white-space: pre-wrap; word-wrap: break-word; }
  .modal-meta { margin-top: 15px; padding-top: 10px; border-top: 1px solid #dfe6e9; font-size: 12px; color: #636e72; }
  .modal-meta span { display: inline-block; margin-right: 15px; }
</style>
</head>

<body>
<h1>�� Evaluation Dashboard</h1>
<div class="subtitle">Live view of evaluation pipeline &middot; Auto-refreshes every 15s &middot; DB: {{ summary.total }} entries</div>

<div class="cards">
  <div class="card total"><div class="num">{{ summary.total }}</div><div class="label">Total</div></div>
  <div class="card completed"><div class="num">{{ summary.completed }}</div><div class="label">Completed</div></div>
  <div class="card pass"><div class="num">{{ summary.pass }}</div><div class="label">Pass (≥3)</div></div>
  <div class="card fail"><div class="num">{{ summary.fail }}</div><div class="label">Fail (<3)</div></div>
  <div class="card pending"><div class="num">{{ summary.status_counts.get('ASSIGNED', 0) + summary.status_counts.get('PENDING', 0) }}</div><div class="label">In Queue</div></div>
  <div class="card unrated"><div class="num">{{ summary.unrated }}</div><div class="label">Unrated</div></div>
</div>

{% if summary.total > 0 %}
<div class="progress-bar">
  <div class="progress-fill" style="width: {{ (summary.completed / summary.total * 100) | round(1) }}%">
    {{ (summary.completed / summary.total * 100) | round(1) }}% Complete
  </div>
</div>
{% endif %}

{% if summary.by_type %}
<div class="by-type">
<h3>By Question Type</h3>
<table>
<tr><th>Question Type</th><th>Total</th><th>Pass</th><th>Fail</th><th>Unrated</th><th>Pass Rate</th></tr>
{% for qt, stats in summary.by_type.items() %}
<tr>
  <td>{{ qt }}</td>
  <td>{{ stats.total }}</td>
  <td style="color:#00b894;font-weight:bold">{{ stats.pass }}</td>
  <td style="color:#d63031;font-weight:bold">{{ stats.fail }}</td>
  <td>{{ stats.unrated }}</td>
  <td>{% if stats.total > 0 %}{{ ((stats.pass / stats.total) * 100) | round(1) }}%{% endif %}</td>
</tr>
{% endfor %}
</table>
</div>
{% endif %}

<h3>All Evaluations</h3>
<table>
<tr>
  <th>ID</th><th>Question</th><th>Type</th><th>Status</th><th>Rating</th><th>Method</th><th>Resp Time</th><th>Answer</th>
</tr>
{% for r in rows %}
<tr>
  <td><a href="/detail/{{ r.id }}">{{ r.id }}</a></td>
  <td>{{ r.question }}</td>
  <td style="font-size:11px">{{ r.question_type }}</td>
  <td><span class="status-badge status-{{ r.status }}">{{ r.status }}</span></td>
  <td>
    {% if r.rating is not none %}
      <span class="rating rating-clickable {{ 'pass' if r.rating|int >= 3 else 'fail' }}"
            onclick="showAnalysis('{{ r.id }}', '{{ r.question | replace("'", "\\'") }}', {{ r.rating }}, '{{ r.judge_method }}', '{{ r.response_time }}', {{ r.analysis | tojson }})"
            title="Click to view judge analysis">{{ r.rating }}</span>
    {% else %}
      <span style="color:#b2bec3">—</span>
    {% endif %}
  </td>

  <td style="font-size:11px">{{ r.judge_method }}</td>
  <td style="font-size:11px">{{ r.response_time }}</td>
  <td style="font-size:12px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{{ r.answer }}">{{ r.answer }}</td>
</tr>
{% endfor %}

</table>

<p class="auto-refresh">Page auto-refreshes every 15 seconds.</p>

<!-- Modal for judge analysis -->
<div class="modal-overlay" id="analysisModal" onclick="if(event.target===this)closeModal()">
  <div class="modal-box">
    <div class="modal-header">
      <div class="modal-title" id="modalTitle">Judge Analysis</div>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div class="modal-body" id="modalBody">No analysis available.</div>
    <div class="modal-meta" id="modalMeta"></div>
  </div>
</div>

<script>
function showAnalysis(evalId, question, rating, method, respTime, analysis) {
  var passClass = rating >= 3 ? 'pass' : 'fail';
  var passLabel = rating >= 3 ? 'PASS' : 'FAIL';
  document.getElementById('modalTitle').innerHTML =
    '<span class="rating ' + passClass + '" style="margin-right:8px">' + rating + '</span>' +
    evalId + ' &mdash; ' + question +
    ' <span class="status-badge status-COMPLETED" style="margin-left:8px">' + passLabel + '</span>';

  if (analysis && analysis.trim()) {
    document.getElementById('modalBody').textContent = analysis;
  } else {
    document.getElementById('modalBody').textContent = 'No analysis available for this evaluation.';
  }

  var metaHtml = '<span><strong>Method:</strong> ' + (method || 'N/A') + '</span>';
  if (respTime) metaHtml += '<span><strong>Response Time:</strong> ' + respTime + 's</span>';
  metaHtml += '<span><a href="/detail/' + evalId + '" style="color:#0984e3">View full detail &rarr;</a></span>';
  document.getElementById('modalMeta').innerHTML = metaHtml;

  document.getElementById('analysisModal').classList.add('active');
}

function closeModal() {
  document.getElementById('analysisModal').classList.remove('active');
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeModal();
});
</script>

</body>
</html>
"""

DETAIL_HTML = r"""

<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Detail — {{ row.id }}</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #f5f6fa; color: #2d3436; }
  h1 { margin-bottom: 5px; }
  h2 { margin-top: 25px; border-bottom: 2px solid #dfe6e9; padding-bottom: 5px; }
  .back { margin-bottom: 15px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .card { background: #fff; border-radius: 10px; padding: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
  .field { margin-bottom: 8px; }
  .field-label { font-weight: bold; color: #636e72; font-size: 12px; text-transform: uppercase; }
  .field-value { font-size: 14px; }
  .rating-big { font-size: 48px; font-weight: bold; }
  .rating-big.pass { color: #00b894; }
  .rating-big.fail { color: #d63031; }
  pre { background: #2d3436; color: #dfe6e9; padding: 15px; border-radius: 8px; overflow-x: auto; font-size: 12px; }
  img { max-width: 100%; border-radius: 8px; }
  audio { width: 100%; margin-top: 10px; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; }
  .badge.pass { background: #00b894; color: #fff; }
  .badge.fail { background: #d63031; color: #fff; }
  .badge.none { background: #dfe6e9; color: #636e72; }
</style>
</head>
<body>
<div class="back"><a href="/">← Back to Dashboard</a></div>
<h1>{{ row.id }}: {{ row.question }}</h1>

<div class="grid">
  <div class="card">
    <h2>Result</h2>
    {% if result.rating is not none %}
      <div class="rating-big {{ 'pass' if result.rating|int >= 3 else 'fail' }}">{{ result.rating }}</div>
      <div class="badge {{ 'pass' if result.rating|int >= 3 else 'fail' }}">
        {{ 'PASS' if result.rating|int >= 3 else 'FAIL' }}
      </div>
    {% else %}
      <div class="rating-big" style="color:#636e72">N/A</div>
      <div class="badge none">UNRATED</div>
    {% endif %}
    
    <div class="field" style="margin-top:15px">
      <div class="field-label">Judge Method</div>
      <div class="field-value">{{ result.meta.get('judge_method', 'N/A') }}</div>
    </div>
    <div class="field">
      <div class="field-label">Response Time</div>
      <div class="field-value">{{ result.meta.get('response_time', 'N/A') }}s</div>
    </div>
    <div class="field">
      <div class="field-label">Duration</div>
      <div class="field-value">{{ result.meta.get('duration', 'N/A') }}s</div>
    </div>
    <div class="field">
      <div class="field-label">Error Type</div>
      <div class="field-value">{{ result.meta.get('error_type', 'N/A') }}</div>
    </div>
    {% if result.meta.get('entropy_metrics') %}
    <div class="field">
      <div class="field-label">Entropy Metrics</div>
      <div class="field-value">
        entropy={{ result.meta.entropy_metrics.entropy | round(4) }},
        surprisal={{ result.meta.entropy_metrics.surprisal | round(4) }},
        curvature={{ result.meta.entropy_metrics.curvature | round(4) }}
      </div>
    </div>
    {% endif %}
  </div>

  <div class="card">
    <h2>AI Response</h2>
    <div class="field">
      <div class="field-label">Transcribed Answer</div>
      <div class="field-value" style="font-size:16px;font-style:italic;">"{{ result.meta.get('answer', 'N/A') }}"</div>
    </div>
    <div class="field">
      <div class="field-label">Question Type</div>
      <div class="field-value">{{ result.meta.get('question_type', 'N/A') }}</div>
    </div>
    <div class="field">
      <div class="field-label">Eval Type</div>
      <div class="field-value">{{ result.meta.get('eval_type', 'N/A') }}</div>
    </div>
    <div class="field">
      <div class="field-label">Reference</div>
      <div class="field-value">{{ result.meta.get('reference', 'N/A') }}</div>
    </div>
  </div>
</div>

<h2>Judge Analysis</h2>
<div class="card">
  <pre>{{ result.analysis }}</pre>
</div>

{% if judge_prompt %}
<h2>Judge Prompt <span style="font-size:14px;color:#636e72">(sent to VLM/LLM)</span></h2>
<div class="card">
  <pre style="max-height:600px;overflow-y:auto">{{ judge_prompt }}</pre>
</div>
{% elif result.meta.get('judge_prompt_path') %}
<h2>Judge Prompt</h2>
<div class="card">
  <p style="color:#636e72">Prompt file path: {{ result.meta.get('judge_prompt_path') }}</p>
</div>
{% elif result.meta.get('judge_method') == 'deterministic' %}
<h2>Judge Prompt</h2>
<div class="card">
  <p style="color:#636e72">No VLM prompt — this case was evaluated deterministically (no LLM called).</p>
</div>
{% endif %}

  <h2>Media</h2>

  <div class="grid">
    <div class="card">
      <h3>Input Image</h3>
      {% if meta.image_path %}
        <img src="/asset?path={{ meta.image_path }}" alt="Input image">
      {% else %}
        <p style="color:#636e72">No image</p>
      {% endif %}
    </div>
    
    <!-- Pre-State Screenshots (Human Interpretability) -->
    {% if meta.pre_state_screenshots %}
    <div class="card">
      <h3>Pre-State Screenshots ({{ meta.pre_state_screenshots|length }})</h3>
      {% for ss_path in meta.pre_state_screenshots %}
        <div style="margin-bottom:15px">
          <img src="/asset?path={{ ss_path }}" alt="Pre-state" style="max-width:100%;border-radius:8px">
          <p style="font-size:11px;color:#636e72;margin-top:5px">Pre-state {{ loop.index }}</p>
        </div>
      {% endfor %}
    </div>
    {% endif %}
    
    <!-- Post-State Screenshots (Judge Evidence) -->
    {% if meta.post_state_screenshots %}
    <div class="card">
      <h3>Post-State Screenshots ({{ meta.post_state_screenshots|length }})</h3>
      {% for ss_path in meta.post_state_screenshots %}
        <div style="margin-bottom:15px">
          <img src="/asset?path={{ ss_path }}" alt="Post-state" style="max-width:100%;border-radius:8px">
          <p style="font-size:11px;color:#636e72;margin-top:5px">Post-state {{ loop.index }}</p>
        </div>
      {% endfor %}
    </div>
    {% endif %}
    
    <!-- Fallback: Old app_screenshot_path for backward compat -->
    {% if meta.app_screenshot_path and not meta.post_state_screenshots %}
    <div class="card">
      <h3>Companion Screenshot (Legacy)</h3>
      <img src="/asset?path={{ meta.app_screenshot_path }}" alt="Companion screenshot" style="max-width:100%;border-radius:8px">
    </div>
    {% endif %}
    
    <div class="card">
      <h3>Question Audio</h3>
      {% if meta.audio_raw_path %}
        <audio controls src="/asset?path={{ meta.audio_raw_path }}"></audio>
      {% else %}
        <p style="color:#636e72">No audio</p>
      {% endif %}
      <h3 style="margin-top:15px">Decoded Audio</h3>
      {% if meta.audio_decoded_path %}
        <audio controls src="/asset?path={{ meta.audio_decoded_path }}"></audio>
      {% else %}
        <p style="color:#636e72">No decoded audio</p>
      {% endif %}
    </div>
    <div class="card">
      <h3>AI Response Audio</h3>
      {% if meta.response_path %}
        <audio controls src="/asset?path={{ meta.response_path }}"></audio>
      {% else %}
        <p style="color:#636e72">No response audio</p>
      {% endif %}
    </div>
  </div>


<h2>Device State</h2>
<div class="grid">
  <div class="card">
    <h3>Pre-State</h3>
    <pre>{{ meta.get('device_info_pre', {}) | tojson(indent=2) }}</pre>
  </div>
  <div class="card">
    <h3>Post-State</h3>
    <pre>{{ meta.get('device_info_post', {}) | tojson(indent=2) }}</pre>
  </div>
</div>

{% if meta.get('device_info_state') %}
<h2>Device Info State</h2>
<div class="card">
  <pre>{{ meta.get('device_info_state', {}) | tojson(indent=2) }}</pre>
</div>
{% endif %}

{% if meta.get('extra_logs') %}
<h2>Extra Logs</h2>
<div class="card">
  <pre>{{ meta.get('extra_logs', {}) | tojson(indent=2) }}</pre>
</div>
{% endif %}

{% if meta.get('jinju_log_path') %}
<h2>Logcat</h2>
<div class="card">
  <iframe src="/asset?path={{ meta.jinju_log_path }}" style="width:100%;height:400px;border:none;"></iframe>
</div>
{% endif %}

</body>
</html>
"""


# ── Main ────────────────────────────────────────────────────────────

def main():
    global DB_PATH, RESULTS_ROOT
    parser = argparse.ArgumentParser(description="Live Evaluation Dashboard")
    parser.add_argument("--db", default="metric_coordinator/queue.db", help="Path to queue.db")
    parser.add_argument("--port", type=int, default=5055, help="Port to serve on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--results-root", default="data/results", help="Root results directory")
    args = parser.parse_args()

    DB_PATH = args.db
    RESULTS_ROOT = args.results_root

    if not os.path.isfile(DB_PATH):
        print(f"ERROR: Database not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"�� Starting dashboard on http://localhost:{args.port}")
    print(f"   DB: {DB_PATH}")
    print(f"   Results root: {RESULTS_ROOT}")
    app.run(host=args.host, port=args.port, debug=True)


if __name__ == "__main__":
    main()
