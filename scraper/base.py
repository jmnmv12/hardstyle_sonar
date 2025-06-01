from abc import ABC, abstractmethod
from datetime import datetime
from typing import List
from scraper.models import TrackData


class BaseScraper(ABC):

    from_date: datetime

    def __init__(self, from_date: datetime):
        self.from_date = from_date

    @abstractmethod
    def fetch_tracks(self) -> List[TrackData]:
        raise NotImplementedError
