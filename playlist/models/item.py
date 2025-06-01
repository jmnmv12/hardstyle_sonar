from datetime import datetime
from enum import Enum


class Item:
    id: str
    release_date: datetime

    def __init__(self, id: str, release_date: str = None):
        self.id = id
        self.release_date = None

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other) -> bool:
        return self.id == other.id

    def __str__(self) -> str:
        return self.id
