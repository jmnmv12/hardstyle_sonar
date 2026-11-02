from datetime import datetime
from enum import Enum


class Item:
    id: str
    release_date: datetime

    def __init__(self, id: str, release_date=None):
        self.id = id
        self.release_date = self._parse_date(release_date)

    @staticmethod
    def _parse_date(value):
        """Parse a date passed as an ISO 8601 string (e.g. YouTube publishedAt)."""
        if value is None or isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other) -> bool:
        return self.id == other.id

    def __str__(self) -> str:
        return self.id
