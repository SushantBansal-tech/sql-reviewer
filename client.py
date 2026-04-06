"""
client.py — Python client for the SQL Query Reviewer environment.

Supports both async (recommended) and sync usage:

    # Async — used in inference.py and training loops
    async with SQLReviewEnv(base_url="https://your-space.hf.space") as env:
        result = await env.reset()
        result = await env.step(SQLReviewAction(fixed_query="SELECT ..."))

    # Sync — used in notebooks and quick tests
    with SQLReviewEnv(base_url="https://your-space.hf.space").sync() as env:
        result = env.reset()
        result = env.step(SQLReviewAction(fixed_query="SELECT ..."))

    # Docker — used by inference.py when LOCAL_IMAGE_NAME is set
    env = await SQLReviewEnv.from_docker_image("sql-review-env:latest")
    result = await env.reset()
    await env.close()
"""

from openenv.core.env_client import EnvClient
from openenv.core.client_types import StepResult
from models import SQLReviewAction, SQLReviewObservation, SQLReviewState
# OR use absolute import if models is at root level


class SQLReviewEnv(EnvClient[SQLReviewAction, SQLReviewObservation, SQLReviewState]):
    """
    Client for the SQL Query Reviewer OpenEnv environment.

    Inherits from EnvClient which provides:
      - async reset() / step() / state() / close()
      - .sync() wrapper for synchronous usage
      - from_docker_image() class method for Docker-based usage
      - WebSocket connection management
    """

    def _step_payload(self, action: SQLReviewAction) -> dict:
        """Serialize action → dict for the wire format."""
        return {
            "fixed_query":  action.fixed_query,
            "explanation":  action.explanation or "",
        }

    def _parse_result(self, payload: dict) -> StepResult:
        """Deserialize wire format → typed StepResult."""
        obs = SQLReviewObservation(
            task_id            = payload.get("task_id", ""),
            difficulty         = payload.get("difficulty", ""),
            broken_query       = payload.get("broken_query", ""),
            schema_context     = payload.get("schema_context", ""),
            error_description  = payload.get("error_description", ""),
            expected_behavior  = payload.get("expected_behavior", ""),
            attempts_remaining = payload.get("attempts_remaining", 0),
            last_score         = payload.get("last_score"),
            last_feedback      = payload.get("last_feedback"),
            done               = payload.get("done", False),
            reward             = payload.get("reward"),
        )
        return StepResult(
            observation = obs,
            reward      = payload.get("reward", 0.0) or 0.0,
            done        = payload.get("done", False),
        )

    def _parse_state(self, payload: dict) -> SQLReviewState:
        """Deserialize wire format → typed State."""
        return SQLReviewState(
            episode_id          = payload.get("episode_id"),
            step_count          = payload.get("step_count", 0),
            current_task_id     = payload.get("current_task_id"),
            current_difficulty  = payload.get("current_difficulty"),
            cumulative_reward   = payload.get("cumulative_reward", 0.0),
        )