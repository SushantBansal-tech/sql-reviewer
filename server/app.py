"""
server/app.py — FastAPI server + Gradio UI for the SQL Review environment.
"""

import sys
import os
import json
import subprocess
import gradio as gr
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

# Ensure local modules are discoverable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

# ── Standard OpenEnv App Initialization ──────────────────
app = create_fastapi_app(
    env=make_env,
    action_cls=SQLAction,
    observation_cls=SQLObservation,
)

# ── API Endpoints ────────────────────────────────────────

@app.get("/tasks")
def list_tasks():
    """Return all tasks and the action schema."""
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

class GraderRequest(BaseModel):
    task_id: str
    fixed_query: str

@app.post("/grader")
def run_grader(req: GraderRequest):
    """Grade a single query against a specific task."""
    if req.task_id not in TASKS:
        raise HTTPException(status_code=404, detail=f"Unknown task_id '{req.task_id}'")
    _, grader = TASKS[req.task_id]
    score, feedback = grader(req.fixed_query)
    return {"task_id": req.task_id, "score": score, "feedback": feedback, "pass": score >= 0.9}

@app.get("/baseline")
def run_baseline():
    """Runs inference.py against all tasks."""
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "inference.py")
    if not os.path.exists(script):
        raise HTTPException(status_code=500, detail="inference.py not found.")
    try:
        result = subprocess.run(["python", script, "--output-json"], capture_output=True, text=True, timeout=1200)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"inference.py failed: {result.stderr[:500]}")
        return json.loads(result.stdout)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Gradio UI Interface ──────────────────────────────────

def ui_grade_wrapper(task_id, query):
    """Bridge between the UI and your existing grader logic."""
    if not task_id or not query:
        return 0, "Please select a task and enter a query."
    _, grader = TASKS[task_id]
    score, feedback = grader(query)
    return score, feedback

def get_task_details(task_id):
    """Updates the UI with task description when selected."""
    if task_id in TASKS:
        task_def, _ = TASKS[task_id]
        return task_def["expected_behavior"], task_def["difficulty"]
    return "", ""

with gr.Blocks(theme=gr.themes.Soft(), title="SQL Review Admin") as ui:
    gr.Markdown("# 🛠️ SQL Review Environment")
    gr.Markdown("Test your SQL corrections manually or view environment state.")
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Take Action")
            task_dropdown = gr.Dropdown(choices=TASK_ORDER, label="Select Task ID")
            task_desc = gr.Textbox(label="Task Goal", interactive=False)
            diff_display = gr.Label(label="Difficulty")
            
            query_input = gr.Textbox(label="Your Fixed SQL Query", placeholder="SELECT * FROM...", lines=6)
            submit_btn = gr.Button("Step / Grade", variant="primary")
            reset_btn = gr.Button("Reset Environment")

        with gr.Column(scale=1):
            gr.Markdown("### State Observer")
            score_out = gr.Number(label="Last Score (0.0 - 1.0)")
            feedback_out = gr.Textbox(label="Grader Feedback", lines=10, interactive=False)

    # Interactivity
    task_dropdown.change(get_task_details, inputs=task_dropdown, outputs=[task_desc, diff_display])
    submit_btn.click(ui_grade_wrapper, inputs=[task_dropdown, query_input], outputs=[score_out, feedback_out])
    reset_btn.click(lambda: (None, "", 0, "Environment Reset"), outputs=[task_dropdown, query_input, score_out, feedback_out])

# ── Final Integration ────────────────────────────────────

# Mount the Gradio UI to the root of the FastAPI app
app = gr.mount_gradio_app(app, ui, path="/")