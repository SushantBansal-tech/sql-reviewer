"""
server/app.py — FastAPI server for the SQL Review environment.

Exposes:
  Standard OpenEnv:  /ws  /reset  /step  /state  /health  /docs
  Hackathon extras:  /tasks  /grader  /baseline
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from openenv.core.env_server import create_fastapi_app
from server.environment import SQLReviewEnvironment
from server.action import SQLAction
from server.observation import SQLObservation
from tasks import TASKS, TASK_ORDER

def make_env():
    try:
        return SQLReviewEnvironment()
    except Exception as e:
        print("ENV INIT ERROR:", e)
        raise e


# ── Standard OpenEnv app ──────────────────────────────────

app = create_fastapi_app(
    env=make_env,
    action_cls=SQLAction,
    observation_cls=SQLObservation,
)


# ── /tasks — list tasks + action schema ──────────────────
@app.get("/tasks")
def list_tasks():
    """Return all tasks and the action schema (required for /step)."""
    task_list = []
    for task_id in TASK_ORDER:
        task_def, _ = TASKS[task_id]
        task_list.append({
            "task_id": task_def["task_id"],
            "difficulty": task_def["difficulty"],
            "description": task_def["expected_behavior"],
            "error_hint": task_def["error_description"],
        })
    return {
        "tasks": task_list,
        "action_schema": {
            "fixed_query": "string — your corrected SQL query",
            "explanation": "string (optional) — what you changed and why",
        },
        "scoring": "0.0 to 1.0 per task, partial credit awarded",
    }


# ── /grader — score a specific query manually ────────────
class GraderRequest(BaseModel):
    task_id: str
    fixed_query: str


@app.post("/grader")
def run_grader(req: GraderRequest):
    """Grade a single query against a specific task. Useful for testing."""
    if req.task_id not in TASKS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown task_id '{req.task_id}'. "
                   f"Valid: {TASK_ORDER}"
        )
    _, grader = TASKS[req.task_id]
    score, feedback = grader(req.fixed_query)
    return {
        "task_id": req.task_id,
        "score": score,
        "feedback": feedback,
        "pass": score >= 0.9,
    }


# ── /baseline — trigger the inference script ─────────────
@app.get("/baseline")
def run_baseline():
    """
    Runs inference.py against all 3 tasks and returns scores.
    Reads API credentials from environment variables.
    """
    import subprocess
    import json as _json

    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "inference.py"
    )

    if not os.path.exists(script):
        raise HTTPException(status_code=500, detail="inference.py not found.")

    try:
        result = subprocess.run(
            ["python", script, "--output-json"],
            capture_output=True, text=True, timeout=1200
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"inference.py failed: {result.stderr[:500]}"
            )
        scores = _json.loads(result.stdout)
        return scores
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Baseline timed out (>20 min).")
    except _json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="inference.py output was not valid JSON."
        )