"""
inference.py — Baseline agent for the SQL Query Reviewer environment.
================================================================
MANDATORY stdout format (judges parse this exactly):

  [START] task=<task_name> env=<benchmark> model=<model_name>
  [STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
  [END]   success=<true|false> steps=<n> score=<0.000> rewards=<r1,r2,...>

Rules:
  - One [START] line at episode begin
  - One [STEP] line per step, immediately after env.step() returns
  - One [END] line after env.close(), ALWAYS emitted even on exception
  - reward and rewards formatted to 2 decimal places
  - done and success are lowercase: true or false
  - error is the raw error string, or null if none
  - All fields on a single line, no newlines within a line

Environment variables (REQUIRED):
  GEMINI_API_KEY      Your Google Gemini API key (get from https://aistudio.google.com/app/apikeys)
  ENV_URL             Server URL (default: http://localhost:8000)
  MODEL_NAME          Model to use (default: gemini-1.5-flash)
"""

import asyncio
import os
import sys
import textwrap
from typing import List, Optional

# ✅ NEW: Use google.genai instead of deprecated google.generativeai
import google.genai as genai
from google.genai import types


from client import SQLReviewEnv, SQLReviewAction , SQLReviewState


# ── Config from environment variables ──────���─────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME     = os.getenv("MODEL_NAME", "gemini-1.5-flash")
ENV_URL        = os.getenv("ENV_URL", "http://localhost:8000")
TASK_NAME      = os.getenv("SQL_REVIEW_TASK", "sql-query-review")
BENCHMARK      = os.getenv("SQL_REVIEW_BENCHMARK", "sql-review-env")

MAX_STEPS               = 9
TEMPERATURE             = 0.1
MAX_TOKENS              = 400
SUCCESS_SCORE_THRESHOLD = 0.6

# ✅ Validate API key
if not GEMINI_API_KEY:
    print("[ERROR] GEMINI_API_KEY environment variable not set!", flush=True)
    print("[ERROR] Get it from: https://aistudio.google.com/app/apikeys", flush=True)
    sys.exit(1)

# ✅ Configure Gemini with new library
genai.configure(api_key=GEMINI_API_KEY)

# ── System prompt ─────────────────────────────────────────
SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert SQL engineer specialising in query correctness and performance.

    You will receive:
    - A broken SQL query
    - The table schema it operates on
    - A plain-English description of what is wrong
    - What the correct query should do

    Your job: return ONLY the corrected SQL query.
    - No markdown code blocks (no ```sql fences)
    - No explanation text before or after
    - Just the raw corrected SQL

    Key rules:
    - Use IS NULL / IS NOT NULL, never = NULL
    - Use explicit JOIN, never comma-separated tables
    - Select only needed columns, never SELECT *
    - Use COUNT(DISTINCT col) when counting unique values
    - Preserve original WHERE filters unless they are the bug
""").strip()


# ── Logging (exact format judges expect) ──────────────────
def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(
    step: int,
    action: str,
    reward: float,
    done: bool,
    error: Optional[str],
) -> None:
    action_safe = action.replace("\n", " ").strip()[:120]
    error_val   = error if error else "null"
    done_val    = str(done).lower()
    print(
        f"[STEP] step={step} action={action_safe!r} "
        f"reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} "
        f"score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


# ── Build user prompt from observation ───────────────────
def build_prompt(obs) -> str:
    feedback_hint = ""
    if obs.last_feedback:
        feedback_hint += f"\nFeedback from last attempt: {obs.last_feedback}"
    if obs.last_score is not None:
        feedback_hint += f"\nScore so far: {obs.last_score:.2f}/1.0 — improve on this"

    return textwrap.dedent(f"""
        Table schema:
        {obs.schema_context}

        Broken SQL query:
        {obs.broken_query}

        What is wrong:
        {obs.error_description}

        What the fixed query must do:
        {obs.expected_behavior}
        {feedback_hint}

        Return ONLY the corrected SQL:
    """).strip()


# ── Call Gemini API ──────────────────────────────────────
def get_fixed_query(obs, history: List[str]) -> str:
    """Call Google Gemini API using new google.genai library"""
    try:
        # ✅ Use new google.genai API
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=types.ContentsType([
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(build_prompt(obs))]
                )
            ]),
            config=types.GenerateContentConfig(
                temperature=TEMPERATURE,
                max_output_tokens=MAX_TOKENS,
                system_instruction=SYSTEM_PROMPT,
            )
        )
        
        text = response.text.strip()
        
        # Strip accidental markdown fences
        if text.startswith("```"):
            text = "\n".join(
                line for line in text.split("\n")
                if not line.strip().startswith("```")
            ).strip()
        
        return text if text else "SELECT 1"
    
    except Exception as exc:
        print(f"[DEBUG] Gemini call failed: {exc}", flush=True)
        return "SELECT 1"


# ── Main async episode ────────────────────────────────────
async def main() -> None:
    print(f"[DEBUG] Using Gemini model: {MODEL_NAME}", flush=True)
    print(f"[DEBUG] Connecting to env at: {ENV_URL}", flush=True)
    
    env = SQLReviewEnv(base_url=ENV_URL)

    history: List[str] = []
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    log_start(task=TASK_NAME, env=BENCHMARK, model=MODEL_NAME)

    try:
        # Start a new episode
        result = await env.reset()
        obs    = result.observation

        for step in range(1, MAX_STEPS + 1):
            if result.done:
                break

            # Agent generates a fixed SQL query using Gemini
            fixed_query = get_fixed_query(obs, history)

            error = None
            try:
                # Submit the fix to the environment
                result = await env.step(SQLReviewAction(
                    fixed_query=fixed_query,
                    explanation="Baseline agent fix",
                ))
                obs    = result.observation
                reward = result.reward or 0.0
                done   = result.done

            except Exception as exc:
                error  = str(exc)
                reward = 0.0
                done   = False
                print(f"[DEBUG] step() error: {exc}", flush=True)

            rewards.append(reward)
            steps_taken = step

            # MANDATORY: one [STEP] line per step
            log_step(
                step=step,
                action=fixed_query,
                reward=reward,
                done=done,
                error=error,
            )

            history.append(
                f"step={step} score={getattr(obs, 'last_score', '?')} "
                f"reward={reward:+.2f}"
            )

            if done:
                break

        # Compute final score clamped to [0, 1]
        if rewards:
            score   = sum(rewards) / len(rewards)
            score   = min(max(score, 0.0), 1.0)
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as exc:
        print(f"[DEBUG] Episode error: {exc}", flush=True)

    finally:
        # Always close the env and always emit [END]
        try:
            await env.close()
        except Exception as exc:
            print(f"[DEBUG] env.close() error: {exc}", flush=True)

        log_end(
            success=success,
            steps=steps_taken,
            score=score,
            rewards=rewards,
        )


if __name__ == "__main__":
    asyncio.run(main())