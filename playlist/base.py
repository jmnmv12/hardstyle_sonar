from abc import ABC, abstractmethod
from typing import List
from playlist.models import Item


class BasePlaylistService(ABC):
    playlist_id: str

    def __init__(self, playlist_id: str):
        self.playlist_id = playlist_id

    @abstractmethod
    def _authenticate(self):
        raise NotImplementedError

    @abstractmethod
    def get_playlist(self) -> List[Item]:
        raise NotImplementedError

    @abstractmethod
    def remove_playlist_items(self):
        raise NotImplementedError

    @abstractmethod
    def add_playlist_items(self):
        raise NotImplementedError

    @abstractmethod
    def get_track(self):
        raise NotImplementedError
