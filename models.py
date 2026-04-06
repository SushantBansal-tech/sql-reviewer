"""
models.py — Pydantic models for the SQL Query Reviewer environment.
Uses openenv.core.env_server.types as base classes (Pydantic, not dataclasses).
"""

from typing import Optional, Any, Dict
from pydantic import Field
from openenv.core.env_server.types import Action, Observation, State


class SQLReviewAction(Action):
    """What the agent submits — a corrected SQL query."""
    fixed_query: str = Field(..., description="The corrected SQL query")
    explanation: Optional[str] = Field(
        default=None,
        description="Optional explanation of what was fixed"
    )


class SQLReviewObservation(Observation):
    """What the agent sees at each step."""
    task_id: str = Field(default="", description="Current task identifier")
    difficulty: str = Field(default="", description="easy | medium | hard")
    broken_query: str = Field(default="", description="The SQL query to fix")
    schema_context: str = Field(default="", description="Relevant table schemas")
    error_description: str = Field(default="", description="Plain English bug description")
    expected_behavior: str = Field(default="", description="What the correct query should do")
    attempts_remaining: int = Field(default=0, description="Attempts left on this task")
    last_score: Optional[float] = Field(default=None, description="Score of last attempt")
    last_feedback: Optional[str] = Field(default=None, description="Grader feedback")
    # done and reward are inherited from Observation base class


class SQLReviewState(State):
    """Internal episode metadata."""
    # episode_id and step_count inherited from State base class
    current_task_id: Optional[str] = Field(default=None)
    current_difficulty: Optional[str] = Field(default=None)
    cumulative_reward: float = Field(default=0.0)
    max_attempts: int = Field(default=3)