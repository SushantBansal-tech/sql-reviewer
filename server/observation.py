# server/observation.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class SQLObservation:
    task_id: str
    score: float
    feedback: str
    done: bool
