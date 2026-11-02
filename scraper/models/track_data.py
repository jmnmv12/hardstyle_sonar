from datetime import datetime
from enum import Enum


class Genre(Enum):
    Unknown = 0
    Hardstyle = 1
    Hardcore = 2


class TrackData:

    spotify_uri: str = None
    youtube_video_id: str = None
    title: str
    artist_name: str
    release_date: datetime
    genre: Genre = Genre.Hardstyle

    def __init__(
        self,
        track_name=None,
        artist_name=None,
        track_date=None,
        genre=None,
        youtube_video_id=None,
    ):
        self.title: str = track_name
        self.artist_name: str = artist_name
        self.release_date: datetime = track_date
        self.genre: Genre = genre
        self.youtube_video_id: str = youtube_video_id

    def __hash__(self) -> int:
        return hash((self.title, self.artist_name))

    def __eq__(self, other) -> bool:
        return self.title == other.title and self.artist_name == other.artist_name
