"""
models.py — Typed contracts for the SQL Query Review environment.

The agent sees a broken/inefficient SQL query and must return a corrected version.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from openenv.core.env_server import Action, Observation, State


@dataclass
class SQLReviewAction(Action):
    """
    The agent submits a corrected SQL query.
    
    Fields:
        fixed_query  : The agent's corrected SQL string.
        explanation  : Optional explanation of what was wrong and what was fixed.
    """
    fixed_query: str
    explanation: Optional[str] = None


@dataclass
class SQLReviewObservation(Observation):
    """
    What the agent sees at each step.

    Fields:
        task_id            : Unique identifier for the current task.
        difficulty         : "easy" | "medium" | "hard"
        broken_query       : The SQL query the agent must fix.
        schema_context     : The table schema relevant to this query.
        error_description  : Human-readable description of what's wrong.
        expected_behavior  : What the corrected query should do.
        attempts_remaining : How many fix attempts are left.
        last_score         : Score of the previous attempt (None if first).
        last_feedback      : Feedback from the grader on the previous attempt.
        done               : Whether the episode is complete.
        reward             : Reward for the last action (None if first step).
    """
    task_id: str
    difficulty: str
    broken_query: str
    schema_context: str
    error_description: str
    expected_behavior: str
    attempts_remaining: int
    last_score: Optional[float] = None
    last_feedback: Optional[str] = None
    done: bool = False
    reward: Optional[float] = None


@dataclass
class SQLReviewState(State):
    """
    Internal episode metadata.
    """
    episode_id: Optional[str] = None
    step_count: int = 0
    current_task_id: Optional[str] = None
    current_difficulty: Optional[str] = None
    cumulative_reward: float = 0.0
    max_attempts: int = 3