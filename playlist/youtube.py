import logging
import os
import requests

from datetime import datetime, timedelta, timezone
from playlist import BasePlaylistService
from playlist.models import Item
from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("hardstyle_watcher.playlist.youtubeapi")
load_dotenv()

YOUTUBE_API_BASE_URL = "https://www.googleapis.com/youtube/v3"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# YouTube API error reasons that indicate the video is already present
# in the playlist. Only these errors may be silently skipped when a video
# is added; every other error must be raised.
DUPLICATE_PLAYLIST_ITEM_REASONS = {
    "alreadyExistsInPlaylist",
    "duplicatePlaylistItem",
    "videoAlreadyInPlaylist",
}


class YouTubeItem(Item):
    """A playlist item that also keeps the YouTube playlist item id,
    which is required to remove a video from a playlist."""

    playlist_item_id: str
    added_at: datetime

    def __init__(self, id: str, release_date=None, playlist_item_id: str = None):
        super().__init__(id, release_date)
        self.playlist_item_id = playlist_item_id
        # publishedAt of a playlist item is the moment the video
        # was added to the playlist
        self.added_at = self.release_date


class YouTubeAPI(BasePlaylistService):

    client_id: str
    client_secret: str
    playlist_title: str
    _access_token: str
    _refresh_token: str

    def __init__(
        self,
        client_id: str = None,
        client_secret: str = None,
        refresh_token: str = None,
        playlist_id: str = None,
        playlist_title: str = "Hardstyle Sonar Livesets",
    ):
        super().__init__(playlist_id)
        self.client_id = client_id
        self.client_secret = client_secret
        self.playlist_title = playlist_title
        self._refresh_token = refresh_token or os.getenv("YOUTUBE_REFRESH_TOKEN")
        self._access_token = os.getenv("YOUTUBE_ACCESS_TOKEN")

        if self._refresh_token and not self._access_token:
            self._refresh_authentication()

    @property
    def access_token(self):
        if not self._access_token:
            self._refresh_authentication()
        return self._access_token

    def _authenticate(self):
        self._refresh_authentication()

    def _auth_headers(self):
        return {
            "Authorization": "Bearer " + self.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _refresh_authentication(self):
        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        r = requests.post(YOUTUBE_TOKEN_URL, data=token_data)
        logger.info("Refreshing YouTube authentication")

        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.warning(f"Error authenticating with YouTube: {e}")
            raise e

        self._access_token = r.json()["access_token"]

    def _get(self, endpoint: str, params: dict = None):
        r = requests.get(
            f"{YOUTUBE_API_BASE_URL}/{endpoint}",
            params=params,
            headers=self._auth_headers(),
        )

        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.warning(f"Error calling YouTube API {endpoint}: {e}")
            raise e

        return r.json()

    def ensure_playlist(self) -> str:
        """Reuse the configured playlist, or look it up by title and
        create it when it does not exist yet. Returns the playlist id."""
        if self.playlist_id:
            return self.playlist_id

        if not self.playlist_title:
            raise Exception("No playlist id or playlist title set")

        page_token = None
        while True:
            params = {"part": "snippet", "mine": "true", "maxResults": 50}
            if page_token:
                params["pageToken"] = page_token

            results = self._get("playlists", params)

            for entry in results.get("items", []):
                if entry.get("snippet", {}).get("title") == self.playlist_title:
                    self.playlist_id = entry["id"]
                    logger.info(
                        f"Reusing existing playlist '{self.playlist_title}' "
                        f"({self.playlist_id})"
                    )
                    return self.playlist_id

            page_token = results.get("nextPageToken")
            if not page_token:
                break

        logger.info(
            f"Playlist '{self.playlist_title}' not found, creating it"
        )
        return self.create_playlist(self.playlist_title)

    def create_playlist(
        self,
        title: str,
        description: str = None,
        privacy_status: str = "private",
    ) -> str:
        if description is None:
            description = (
                "Latest livesets scraped by Hardstyle Sonar. "
                "Sets are kept in this playlist for at least 30 days."
            )

        payload = {
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": privacy_status},
        }

        r = requests.post(
            f"{YOUTUBE_API_BASE_URL}/playlists?part=snippet,status",
            json=payload,
            headers=self._auth_headers(),
        )

        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.warning(f"Error creating YouTube playlist: {e}")
            raise e

        self.playlist_id = r.json()["id"]
        logger.info(f"Created playlist '{title}' ({self.playlist_id})")

        return self.playlist_id

    def get_playlist(self) -> list:
        if not self.playlist_id:
            raise Exception("Playlist id not set")

        items = []
        page_token = None
        while True:
            params = {
                "part": "snippet,contentDetails",
                "playlistId": self.playlist_id,
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token

            results = self._get("playlistItems", params)

            for entry in results.get("items", []):
                video_id = entry.get("contentDetails", {}).get("videoId")
                snippet = entry.get("snippet", {})

                if not video_id:
                    # Deleted or private videos show up without a video id.
                    # Keep them (keyed on the playlist item id) so they can
                    # still be aged out of the playlist after the retention
                    # period.
                    items.append(
                        YouTubeItem(
                            id=entry.get("id"),
                            release_date=snippet.get("publishedAt"),
                            playlist_item_id=entry.get("id"),
                        )
                    )
                    continue

                items.append(
                    YouTubeItem(
                        id=video_id,
                        release_date=snippet.get("publishedAt"),
                        playlist_item_id=entry.get("id"),
                    )
                )

            page_token = results.get("nextPageToken")
            if not page_token:
                break

        logger.info(f"Fetched {len(items)} items from playlist {self.playlist_id}")

        return items

    @staticmethod
    def _is_duplicate_playlist_error(response) -> bool:
        """Whether the response is a YouTube API error that indicates the
        video is already present in the playlist."""
        if response.status_code not in (400, 409):
            return False

        try:
            payload = response.json()
        except ValueError:
            return False

        errors = payload.get("error", {}).get("errors", [])
        reasons = {error.get("reason") for error in errors}

        return bool(reasons & DUPLICATE_PLAYLIST_ITEM_REASONS)

    def add_playlist_items(self, tracks: list):
        for track in tracks:
            payload = {
                "snippet": {
                    "playlistId": self.playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": track.id},
                }
            }

            r = requests.post(
                f"{YOUTUBE_API_BASE_URL}/playlistItems?part=snippet",
                json=payload,
                headers=self._auth_headers(),
            )

            if self._is_duplicate_playlist_error(r):
                logger.info(
                    f"{track.id} is already in playlist {self.playlist_id}"
                )
                continue

            try:
                r.raise_for_status()
            except requests.exceptions.HTTPError as e:
                logger.warning(f"Error adding {track.id} to the playlist: {e}")
                raise e

            logger.info(f"Added {track.id} to playlist {self.playlist_id}")

    def remove_playlist_items(self, tracks: list):
        for track in tracks:
            playlist_item_id = getattr(track, "playlist_item_id", None)
            if playlist_item_id is None:
                logger.warning(
                    f"Cannot remove {track.id}: no playlist item id known"
                )
                continue

            r = requests.delete(
                f"{YOUTUBE_API_BASE_URL}/playlistItems",
                params={"id": playlist_item_id},
                headers=self._auth_headers(),
            )

            try:
                r.raise_for_status()
            except requests.exceptions.HTTPError as e:
                logger.warning(
                    f"Error removing {track.id} from the playlist: {e}"
                )
                raise e

            logger.info(f"Removed {track.id} from playlist {self.playlist_id}")

    def get_track(self, video_id: str, from_date: datetime = None):
        results = self._get("videos", {"part": "snippet", "id": video_id})

        if not results.get("items"):
            logger.info(f"Video {video_id} not found on YouTube")
            return None

        published_at = results["items"][0].get("snippet", {}).get("publishedAt")
        logger.info(f"Found video {video_id} on YouTube")

        return YouTubeItem(id=video_id, release_date=published_at)

    @staticmethod
    def _to_naive_utc(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def sync_playlist(
        self,
        playlist_data,
        track_id_list,
        retention_days: int = 30,
        now: datetime = None,
    ):
        """Add the new videos to the playlist and remove the videos that
        have been in the playlist for at least `retention_days` days and
        are no longer part of the latest livesets.

        Videos with an unknown added date are never removed, so every
        video is guaranteed to stay in the playlist for at least
        `retention_days` days."""
        now = self._to_naive_utc(now or datetime.now(timezone.utc))

        playlist_ids = {item.id for item in playlist_data}
        scrape_ids = {item.id for item in track_id_list}

        # Videos in the scrape but not in the playlist need to be added
        to_add = [item for item in track_id_list if item.id not in playlist_ids]
        logger.info(f"Videos to add: {[str(item) for item in to_add]}")

        # Videos in the playlist but not in the scrape can be removed,
        # but only once they have been in the playlist for at least
        # `retention_days` days
        to_remove = []
        for item in playlist_data:
            if item.id in scrape_ids:
                continue

            added_at = getattr(item, "added_at", None) or item.release_date
            if added_at is None:
                logger.info(f"Keeping {item.id}: no added date known")
                continue

            added_at = self._to_naive_utc(added_at)
            if now - added_at < timedelta(days=retention_days):
                logger.info(
                    f"Keeping {item.id}: in the playlist for less than "
                    f"{retention_days} days"
                )
                continue

            to_remove.append(item)

        logger.info(f"Videos to remove: {[str(item) for item in to_remove]}")

        # Remove videos
        self.remove_playlist_items(to_remove)

        # Add videos
        self.add_playlist_items(to_add)
