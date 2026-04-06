"""
server/environment.py — Core game logic for the SQL Review environment.

The agent receives a broken SQL query and must fix it.
- 3 attempts per task
- Partial credit awarded each attempt
- Reward shaped across the episode (not just end-of-episode)
"""

import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import SQLReviewAction, SQLReviewObservation, SQLReviewState
from tasks import TASKS, TASK_ORDER



from openenv.core.env_server import Environment
# from models import SQLReviewAction, SQLReviewObservation, SQLReviewState
# from tasks import TASKS, TASK_ORDER


class SQLReviewEnvironment(Environment):
    """
    Episode flow:
      reset()          → returns the EASY task observation
      step(action)     → grades the fix, returns feedback + reward
                         after 3 attempts OR score >= 0.9, moves to MEDIUM
                         after MEDIUM completes, moves to HARD
                         after HARD completes, done=True
    """

    MAX_ATTEMPTS = 3
    PASS_THRESHOLD = 0.9   # score above this = task passed early

    def __init__(self):
        self._state = SQLReviewState()
        self._task_index = 0
        self._attempts_used = 0
        self._current_task_id = None
        self._best_score = 0.0

    # ─────────────────────────────────────
    # Public API
    # ─────────────────────────────────────

    def reset(self) -> SQLReviewObservation:
        self._task_index = 0
        self._attempts_used = 0
        self._best_score = 0.0
        self._state = SQLReviewState(
            episode_id=str(uuid.uuid4()),
            step_count=0,
            current_task_id=TASK_ORDER[0],
            current_difficulty="easy",
            cumulative_reward=0.0,
            max_attempts=self.MAX_ATTEMPTS,
        )
        self._current_task_id = TASK_ORDER[0]
        return self._build_observation(
            done=False,
            reward=None,
            last_score=None,
            last_feedback=None,
        )

    def step(self, action: SQLReviewAction) -> SQLReviewObservation:
        self._state.step_count += 1
        self._attempts_used += 1

        task_def, grader = TASKS[self._current_task_id]
        score, feedback = grader(action.fixed_query)

        # Reward = score improvement over previous best (partial progress signal)
        improvement = max(0.0, score - self._best_score)
        reward = round(improvement, 3)
        self._best_score = max(self._best_score, score)
        self._state.cumulative_reward += reward

        # Penalise empty or trivially unchanged submissions
        if action.fixed_query.strip() == "" or \
           action.fixed_query.strip() == task_def["broken_query"].strip():
            reward = -0.1
            feedback = "Submission is empty or identical to the broken query."

        # Decide if we advance to the next task
        task_done = (score >= self.PASS_THRESHOLD) or \
                    (self._attempts_used >= self.MAX_ATTEMPTS)

        if task_done:
            self._task_index += 1
            self._attempts_used = 0
            self._best_score = 0.0

        episode_done = self._task_index >= len(TASK_ORDER)

        if not episode_done:
            self._current_task_id = TASK_ORDER[self._task_index]
            self._state.current_task_id = self._current_task_id
            self._state.current_difficulty = TASKS[self._current_task_id][0]["difficulty"]

        return self._build_observation(
            done=episode_done,
            reward=reward,
            last_score=score,
            last_feedback=feedback,
        )

    @property
    def state(self) -> SQLReviewState:
        return self._state

    # ─────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────

    def _build_observation(
        self,
        done: bool,
        reward,
        last_score,
        last_feedback,
    ) -> SQLReviewObservation:
        if done:
            # Episode over — return final summary observation
            return SQLReviewObservation(
                task_id="episode_complete",
                difficulty="—",
                broken_query="",
                schema_context="",
                error_description="",
                expected_behavior="",
                attempts_remaining=0,
                last_score=last_score,
                last_feedback=last_feedback,
                done=True,
                reward=reward,
            )

        task_def, _ = TASKS[self._current_task_id]
        return SQLReviewObservation(
            task_id=task_def["task_id"],
            difficulty=task_def["difficulty"],
            broken_query=task_def["broken_query"],
            schema_context=task_def["schema_context"],
            error_description=task_def["error_description"],
            expected_behavior=task_def["expected_behavior"],
            attempts_remaining=self.MAX_ATTEMPTS - self._attempts_used,
            last_score=last_score,
            last_feedback=last_feedback,
            done=False,
            reward=reward,
        )