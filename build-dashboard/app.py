"""
ATLAS Build Progress Dashboard
Runs on port 3001, reads ralph status + git log + test results
Auto-refreshes every 15 seconds
"""

import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="ATLAS Build Dashboard")

ATLAS_DIR = Path("/home/ubuntu/atlas")
RALPH_DIR = ATLAS_DIR / ".ralph"
TASKS_FILE = ATLAS_DIR / "tasks.json"
IST = timezone(timedelta(hours=5, minutes=30))


def run_cmd(cmd: str, cwd: str = str(ATLAS_DIR)) -> str:
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10, cwd=cwd
        )
        return proc.stdout.strip()
    except (subprocess.TimeoutExpired, OSError) as err:
        return f"error: {err}"


def get_tasks():
    if TASKS_FILE.exists():
        try:
            return json.loads(TASKS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {"chunks": []}
    return {"chunks": []}


def get_ralph_status():
    status_file = RALPH_DIR / "status.json"
    if status_file.exists():
        try:
            return json.loads(status_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def get_ralph_progress():
    progress_file = RALPH_DIR / "progress.json"
    if progress_file.exists():
        try:
            return json.loads(progress_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def get_git_log(n=15):
    log = run_cmd(f"git log --oneline -n {n}")
    return log.split("\n") if log else []


def get_test_results():
    test_output = run_cmd("python3 -m pytest tests/ -v --tb=no -q 2>&1 | tail -20")
    return test_output


def get_live_log(lines=30):
    live_log = RALPH_DIR / "live.log"
    if live_log.exists():
        try:
            all_lines = live_log.read_text().strip().split("\n")
            return all_lines[-lines:]
        except OSError:
            return []
    return []


def get_session_log():
    session_log = ATLAS_DIR / "docs" / "decisions" / "session-log.md"
    if session_log.exists():
        try:
            return session_log.read_text()[-3000:]
        except OSError:
            return ""
    return ""


_STATUS_ICONS = {"done": "✓", "in_progress": "▶", "failed": "✗", "pending": "○"}
_STATUS_COLORS = {
    "done": "#1a9a6c",
    "in_progress": "#0d8a7a",
    "failed": "#d44040",
    "pending": "#9a9aad",
}


def _build_chunk_rows(chunks: list) -> str:
    rows = ""
    for chunk in chunks:
        status = chunk.get("status", "pending")
        icon = _STATUS_ICONS.get(status, "?")
        color = _STATUS_COLORS.get(status, "#6b6b80")
        rows += f'<tr><td style="color:{color};font-weight:600">{icon} {chunk.get("id", "")}</td><td>{chunk.get("name", "")}</td><td style="color:{color}">{status.upper()}</td></tr>\n'
    return rows


def _build_git_rows(git_log: list) -> str:
    rows = ""
    for line in git_log:
        if line.strip():
            parts = line.split(" ", 1)
            sha = parts[0] if parts else ""
            msg = parts[1] if len(parts) > 1 else ""
            rows += f'<tr><td style="font-family:monospace;color:#0d8a7a">{sha}</td><td>{msg}</td></tr>\n'
    return rows


def _gather_dashboard_context() -> dict:
    chunks = get_tasks().get("chunks", [])
    ralph_status = get_ralph_status()
    done = sum(1 for c in chunks if c.get("status") == "done")
    in_progress = sum(1 for c in chunks if c.get("status") == "in_progress")
    failed = sum(1 for c in chunks if c.get("status") == "failed")
    pending = sum(1 for c in chunks if c.get("status") == "pending")
    total = len(chunks)
    current = next((c for c in chunks if c.get("status") == "in_progress"), None)
    return {
        "now": datetime.now(IST).strftime("%d-%b-%Y %H:%M IST"),
        "done": done,
        "in_progress": in_progress,
        "failed": failed,
        "pending": pending,
        "total": total,
        "pct": int((done / total * 100)) if total > 0 else 0,
        "current_name": current.get("name", "—") if current else "No active chunk",
        "current_id": current.get("id", "—") if current else "—",
        "ralph_state": ralph_status.get("state", "unknown"),
        "chunk_rows": _build_chunk_rows(chunks),
        "git_rows": _build_git_rows(get_git_log()),
        "live_html": "<br>".join(
            f'<span style="font-family:monospace;font-size:12px;color:#6b6b80">{line}</span>'
            for line in get_live_log()
        ),
    }


_DASHBOARD_CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'DM Sans', sans-serif; background: #f9f9f7; color: #1a1a2e; padding: 24px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h1 { font-size: 28px; font-weight: 700; }
.time { font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: #9a9aad; }
.grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-bottom: 24px; }
.card { background: white; border: 1px solid #e4e4e8; border-radius: 8px; padding: 20px; }
.card-label { font-family: 'IBM Plex Mono', monospace; font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: #8a7235; margin-bottom: 8px; }
.card-value { font-family: 'IBM Plex Mono', monospace; font-size: 24px; font-weight: 700; }
.card-value.green { color: #1a9a6c; } .card-value.teal { color: #0d8a7a; }
.card-value.red { color: #d44040; } .card-value.amber { color: #c08a20; }
.progress-bar { width: 100%; height: 8px; background: #e4e4e8; border-radius: 4px; margin: 16px 0; }
.progress-fill { height: 100%; background: #0d8a7a; border-radius: 4px; transition: width 0.5s; }
.section { background: white; border: 1px solid #e4e4e8; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.section-title { font-family: 'IBM Plex Mono', monospace; font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: #8a7235; margin-bottom: 12px; }
table { width: 100%; border-collapse: collapse; }
th { font-family: 'IBM Plex Mono', monospace; font-size: 10px; text-transform: uppercase; letter-spacing: 0.8px; color: #9a9aad; text-align: left; padding: 8px 12px; border-bottom: 2px solid #e4e4e8; }
td { font-size: 13px; padding: 8px 12px; border-bottom: 1px solid #f0f0f2; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.current { background: #f0faf7; border: 1px solid #1a9a6c; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.current-label { font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #1a9a6c; text-transform: uppercase; letter-spacing: 2px; }
.current-value { font-size: 16px; font-weight: 600; margin-top: 4px; }
.ralph-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; }
.ralph-running { background: #e8f5ef; color: #1a9a6c; }
.ralph-stopped { background: #fdf0f0; color: #d44040; }
.ralph-unknown { background: #f0f0f2; color: #9a9aad; }
"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    ctx = _gather_dashboard_context()
    ralph_state = ctx["ralph_state"]
    ralph_css = (
        "ralph-running"
        if ralph_state == "running"
        else "ralph-stopped"
        if ralph_state == "stopped"
        else "ralph-unknown"
    )
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>ATLAS Build Dashboard</title>
    <meta http-equiv="refresh" content="15">
    <style>{_DASHBOARD_CSS}</style>
</head>
<body>
    <div class="header">
        <h1>ATLAS Build Dashboard</h1>
        <div>
            <span class="ralph-badge {ralph_css}">
                RALPH: {ralph_state.upper()}
            </span>
            <span class="time">{ctx["now"]} · auto-refresh 15s</span>
        </div>
    </div>

    <div class="progress-bar">
        <div class="progress-fill" style="width: {ctx["pct"]}%"></div>
    </div>

    <div class="grid">
        <div class="card"><div class="card-label">Total Chunks</div><div class="card-value">{ctx["total"]}</div></div>
        <div class="card"><div class="card-label">Completed</div><div class="card-value green">{ctx["done"]}</div></div>
        <div class="card"><div class="card-label">In Progress</div><div class="card-value teal">{ctx["in_progress"]}</div></div>
        <div class="card"><div class="card-label">Failed</div><div class="card-value red">{ctx["failed"]}</div></div>
        <div class="card"><div class="card-label">Pending</div><div class="card-value">{ctx["pending"]}</div></div>
    </div>

    <div class="current">
        <div class="current-label">Currently Building</div>
        <div class="current-value">{ctx["current_id"]} — {ctx["current_name"]}</div>
    </div>

    <div class="two-col">
        <div class="section">
            <div class="section-title">Chunk Progress</div>
            <table><thead><tr><th>Chunk</th><th>Name</th><th>Status</th></tr></thead>
            <tbody>{ctx["chunk_rows"] or '<tr><td colspan="3" style="color:#9a9aad">No chunks defined yet.</td></tr>'}</tbody></table>
        </div>
        <div class="section">
            <div class="section-title">Recent Commits</div>
            <table><thead><tr><th>SHA</th><th>Message</th></tr></thead>
            <tbody>{ctx["git_rows"] or '<tr><td colspan="2" style="color:#9a9aad">No commits yet</td></tr>'}</tbody></table>
        </div>
    </div>

    <div class="section">
        <div class="section-title">Ralph Live Log (last 30 lines)</div>
        {ctx["live_html"] or '<span style="color:#9a9aad;font-size:12px">Ralph not running yet.</span>'}
    </div>
</body>
</html>"""
    return html


@app.get("/api/status")
async def api_status():
    tasks_data = get_tasks()
    chunks = tasks_data.get("chunks", [])
    return {
        "total": len(chunks),
        "done": sum(1 for c in chunks if c.get("status") == "done"),
        "in_progress": sum(1 for c in chunks if c.get("status") == "in_progress"),
        "failed": sum(1 for c in chunks if c.get("status") == "failed"),
        "pending": sum(1 for c in chunks if c.get("status") == "pending"),
        "ralph": get_ralph_status(),
        "current_chunk": next(
            (c for c in chunks if c.get("status") == "in_progress"), None
        ),
        "git_log": get_git_log(5),
    }
