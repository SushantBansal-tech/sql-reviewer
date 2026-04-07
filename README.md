# SQL Query Reviewer — OpenEnv Environment

> An OpenEnv environment where an AI agent identifies and fixes real-world SQL bugs across three levels of difficulty.

[![OpenEnv](https://img.shields.io/badge/OpenEnv-compatible-blue)](https://github.com/meta-pytorch/OpenEnv)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green)](https://www.python.org/)
[![HuggingFace](https://img.shields.io/badge/HuggingFace-Space-yellow)](https://huggingface.co/)

---

## Motivation

Bad SQL is one of the most common and costly problems in software engineering. Missing `IS NULL` checks, N+1 subquery patterns, accidental cartesian joins, and incorrect aggregations silently break production systems and cost engineering teams hours of debugging every week.

This environment trains AI agents to catch and fix these exact bugs — the same mistakes junior and mid-level engineers make daily. Unlike toy environments, every task in this environment maps directly to a real failure pattern found in production codebases.

**Why this is a great RL environment:**
- Sequential decision making across 3 tasks of increasing difficulty
- Partial credit rewards that signal progress on every attempt
- Deterministic, reproducible graders with no ambiguity
- Real-world utility — something companies would actually pay to evaluate agents on

---

## Environment Overview

```
Agent receives broken SQL query + schema + hint
         ↓
Agent submits fixed SQL query
         ↓
Deterministic grader scores 0.0 → 1.0
         ↓
Reward = improvement over previous best attempt
         ↓
After 3 attempts or score ≥ 0.9 → advance to next task
         ↓
Episode ends after all 3 tasks complete
```

---

## Tasks

### Task 1 — Easy: NULL Filter Bug

**Bug type:** Using `= NULL` instead of `IS NULL`

**Why it matters:** `= NULL` never matches anything in SQL. This is one of the most common mistakes beginners make and silently returns zero rows.

**Broken query:**
```sql
SELECT id, customer_id, total
FROM orders
WHERE status = NULL
ORDER BY created_at DESC;
```

**What the fix must do:** Return all orders where status has no value, sorted by creation date descending.

**Grader breakdown:**
| Criterion | Points |
|---|---|
| Uses `IS NULL` instead of `= NULL` | +0.5 |
| Queries the correct table (`orders`) | +0.3 |
| Preserves `ORDER BY created_at DESC` | +0.2 |
| **Max score** | **1.0** |

---

### Task 2 — Medium: N+1 Query Pattern

**Bug type:** Correlated subqueries inside SELECT running once per row

**Why it matters:** For 1000 order items, this query fires 2001 database queries instead of 1. This is the N+1 problem — one of the biggest performance killers in real applications.

**Broken query:**
```sql
SELECT
    oi.id,
    oi.order_id,
    oi.quantity,
    (SELECT name FROM products WHERE id = oi.product_id) AS product_name,
    (SELECT category FROM products WHERE id = oi.product_id) AS product_category
FROM order_items oi
WHERE oi.quantity > 5;
```

**What the fix must do:** Return the same data using a single JOIN query instead of correlated subqueries.

**Grader breakdown:**
| Criterion | Points |
|---|---|
| Uses explicit `JOIN` to eliminate N+1 | +0.4 |
| Selects both `name` and `category` | +0.2 |
| Preserves `WHERE quantity > 5` filter | +0.2 |
| No correlated subqueries remain | +0.2 |
| **Max score** | **1.0** |

---

### Task 3 — Hard: Four Bugs in One Query

**Bug type:** Cartesian join + `SELECT *` + wrong `COUNT` + wrong `GROUP BY`

**Why it matters:** Each bug alone is bad. Together, they produce a query that returns completely wrong results, on the wrong data, grouped incorrectly, and slower than necessary.

**Broken query:**
```sql
SELECT *, COUNT(*) as order_count
FROM orders, customers
WHERE orders.total > 100
GROUP BY orders.status;
```

**The 4 bugs:**
1. Comma-separated tables create a **cartesian product** — every order matched with every customer
2. `SELECT *` fetches all columns including unnecessary large ones
3. `COUNT(*)` counts duplicates — should be `COUNT(DISTINCT customer_id)`
4. `GROUP BY orders.status` is wrong — goal is per-region stats

**What the fix must do:** For each customer region, return the region name, count of distinct customers, and total revenue from orders over 100 — using an explicit JOIN on the correct key.

**Grader breakdown:**
| Criterion | Points |
|---|---|
| Uses explicit `JOIN` (no cartesian product) | +0.25 |
| Uses `COUNT(DISTINCT ...)` | +0.25 |
| Uses `GROUP BY region` not `GROUP BY status` | +0.25 |
| Removes `SELECT *` | +0.15 |
| Correct join key (`orders.customer_id = customers.id`) | +0.10 |
| **Max score** | **1.0** |

---

## Action Space

The agent submits a JSON action with one required field and one optional field:

```json
{
  "fixed_query": "SELECT id FROM orders WHERE status IS NULL ORDER BY created_at DESC",
  "explanation": "Changed = NULL to IS NULL (optional field)"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `fixed_query` | string | Yes | The corrected SQL query |
| `explanation` | string | No | Why the original was wrong |

---

## Observation Space

At each step the agent receives:

```json
{
  "task_id": "easy_null_filter",
  "difficulty": "easy",
  "broken_query": "SELECT id FROM orders WHERE status = NULL ...",
  "schema_context": "Table: orders\n  id INTEGER PRIMARY KEY\n  ...",
  "error_description": "This query uses = NULL which never matches anything...",
  "expected_behavior": "Return all orders where status is NULL, sorted by...",
  "attempts_remaining": 3,
  "last_score": 0.8,
  "last_feedback": "Correct: uses IS NULL. | Has ORDER BY but wrong column.",
  "done": false,
  "reward": 0.8
}
```

| Field | Type | Description |
|---|---|---|
| `task_id` | string | Unique ID of the current task |
| `difficulty` | string | `easy`, `medium`, or `hard` |
| `broken_query` | string | The SQL query the agent must fix |
| `schema_context` | string | Table definitions relevant to this query |
| `error_description` | string | Plain English description of the bug(s) |
| `expected_behavior` | string | What the correct query should return |
| `attempts_remaining` | int | How many attempts are left on this task |
| `last_score` | float | Score of the previous attempt (null on first step) |
| `last_feedback` | string | Detailed grader feedback on previous attempt |
| `done` | bool | Whether the full episode is complete |
| `reward` | float | Reward for the last action |

---

## Reward Function

```
reward = max(0, current_score - best_previous_score_on_this_task)
```

This rewards **improvement**, not just the final score. If an agent scores 0.5 on attempt 1 and 0.8 on attempt 2, the rewards are `0.5` then `0.3` (the improvement).

**Special cases:**
- Empty submission or unchanged query → reward = `-0.1`
- Score ≥ 0.9 → task passed early, advance to next task
- After 3 attempts → advance to next task regardless of score

This design provides a continuous signal across the full trajectory, not just a binary end-of-episode reward.

---

## File Structure

```
sql-query-reviewer/
├── models.py              ← Pydantic types: Action, Observation, State
├── tasks.py               ← 3 tasks + deterministic graders
├── client.py              ← Async/sync Python client
├── inference.py           ← Baseline agent (HuggingFace LLM via OpenAI client)
├── openenv.yaml           ← Environment manifest
├── requirements.txt       ← Dependencies
├── README.md              ← This file
└── server/
    ├── __init__.py
    ├── environment.py     ← reset() / step() / state() game logic
    ├── app.py             ← FastAPI server + /tasks /grader /baseline
    └── Dockerfile         ← Container definition for HF Space
```

---

## Setup and Usage

### Prerequisites

- Python 3.10+
- Docker (for containerized deployment)
- A HuggingFace account and API token

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run locally

```bash
# From the project root folder
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000/docs` to test all endpoints interactively.

### Run with Docker

```bash
# Build the image
docker build -t sql-review-env -f server/Dockerfile .

# Run the container
docker run -p 8000:8000 \
  -e HF_TOKEN=your_token \
  -e MODEL_NAME=Qwen/Qwen2.5-72B-Instruct \
  sql-review-env
```

### Run the baseline agent

```bash
# Windows
set HF_TOKEN=hf_your_token_here
set MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
set ENV_URL=http://localhost:8000
python inference.py

# Mac / Linux
export HF_TOKEN=hf_your_token_here
export MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
export ENV_URL=http://localhost:8000
python inference.py
```

Expected output:
```
[START] task=sql-query-review env=sql-review-env model=Qwen/Qwen2.5-72B-Instruct
[STEP] step=1 action='SELECT id FROM orders WHERE status IS NULL ...' reward=0.80 done=false error=null
[STEP] step=2 action='SELECT oi.id, p.name FROM order_items oi JOIN ...' reward=0.40 done=false error=null
[STEP] step=3 action='SELECT c.region, COUNT(DISTINCT o.customer_id) ...' reward=0.50 done=true error=null
[END] success=true steps=3 score=0.567 rewards=0.80,0.40,0.50
```

### Use the Python client

```python
import asyncio
from client import SQLReviewEnv, SQLReviewAction

async def main():
    async with SQLReviewEnv(base_url="http://localhost:8000") as env:
        # Start episode
        result = await env.reset()
        obs = result.observation
        print("Task:", obs.task_id)
        print("Broken query:", obs.broken_query)

        # Submit a fix
        result = await env.step(SQLReviewAction(
            fixed_query="SELECT id FROM orders WHERE status IS NULL ORDER BY created_at DESC",
            explanation="Fixed = NULL to IS NULL"
        ))
        print("Score:", result.observation.last_score)    # 1.0
        print("Feedback:", result.observation.last_feedback)
        print("Reward:", result.reward)

asyncio.run(main())
```

For synchronous usage:
```python
from client import SQLReviewEnv, SQLReviewAction

with SQLReviewEnv(base_url="http://localhost:8000").sync() as env:
    result = env.reset()
    result = env.step(SQLReviewAction(fixed_query="SELECT id FROM orders WHERE status IS NULL"))
    print(result.observation.last_score)
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/reset` | Start a new episode |
| `POST` | `/step` | Submit a fixed SQL query |
| `GET` | `/state` | Get current episode metadata |
| `GET` | `/tasks` | List all 3 tasks + action schema |
| `POST` | `/grader` | Score any query against a specific task |
| `GET` | `/baseline` | Trigger inference.py and return scores |
| `GET` | `/health` | Liveness check |
| `GET` | `/docs` | Interactive Swagger API docs |

### Example: Test the grader directly

```bash
curl -X POST http://localhost:8000/grader \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "easy_null_filter",
    "fixed_query": "SELECT id FROM orders WHERE status IS NULL ORDER BY created_at DESC"
  }'
```

Response:
```json
{
  "task_id": "easy_null_filter",
  "score": 1.0,
  "feedback": "Correct: uses IS NULL. | Correct: queries the orders table. | Correct: sorted by created_at DESC.",
  "pass": true
}
```

### Example: List all tasks

```bash
curl http://localhost:8000/tasks
```

---

## Environment Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `HF_TOKEN` | — | Yes (for inference.py) | HuggingFace API key |
| `API_BASE_URL` | `https://router.huggingface.co/v1` | No | LLM API endpoint |
| `MODEL_NAME` | `Qwen/Qwen2.5-72B-Instruct` | No | Model to use for inference |
| `ENV_URL` | `http://localhost:8000` | No | Environment server URL |

---

## Baseline Scores

Tested with `Qwen/Qwen2.5-72B-Instruct` via HuggingFace router:

| Task | Difficulty | Score |
|---|---|---|
| `easy_null_filter` | Easy | 1.00 |
| `medium_n_plus_one` | Medium | 0.80 |
| `hard_multi_bug` | Hard | 0.65 |
| **Average** | — | **0.82** |

---

## Pre-Submission Validation

Run the official validator before submitting:

```bash
# Make sure your HF Space is running, then:
chmod +x validate-submission.sh
./validate-submission.sh https://your-space.hf.space .
```

All 3 checks must pass:
- HF Space responds to `POST /reset` with HTTP 200
- `docker build` completes without errors
- `openenv validate` passes

---

## License

MIT
