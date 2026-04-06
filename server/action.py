# server/action.py
from dataclasses import dataclass

@dataclass
class SQLAction:
    fixed_query: str
    explanation: str = ""
