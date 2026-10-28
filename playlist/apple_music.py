import os
import time
import logging
from datetime import datetime
from typing import List, Optional

import jwt
import requests
from dotenv import load_dotenv

from playlist import BasePlaylistService
from playlist.models import Item

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("hardstyle_watcher.playlist.applemusic")
load_dotenv()


class AppleMusicAPI(BasePlaylistService):
    """Playlist service implementation for Apple Music (MusicKit).

    Authentication uses a developer token (an ES256 signed JWT created with
    the private key from an Apple Music API key) combined with a Music User
    Token for the user library endpoints.
    """

    API_BASE_URL = "https://api.music.apple.com/v1"
    DEVELOPER_TOKEN_LIFETIME = 60 * 60 * 24 * 180  # Apple allows max 180 days

    key_id: str
    team_id: str
    storefront: str
    playlist_name: str

    _private_key: str
    _developer_token: str
    _user_token: str

    def __init__(
        self,
        key_id: str = None,
        team_id: str = None,
        private_key: str = None,
        private_key_path: str = None,
        user_token: str = None,
        playlist_id: str = None,
        playlist_name: str = "Hardstyle Releases",
        storefront: str = "nl",
    ):
        super().__init__(playlist_id)
        self.key_id = key_id
        self.team_id = team_id
        self._private_key = self._load_private_key(private_key, private_key_path)
        self._user_token = user_token
        self._developer_token = None
        self.playlist_name = playlist_name
        self.storefront = storefront

    @staticmethod
    def _load_private_key(private_key: str, private_key_path: str):
        if private_key:
            # Environment variables commonly carry escaped newlines
            return private_key.replace("\\n", "\n")
        if private_key_path and os.path.isfile(private_key_path):
            with open(private_key_path, "r") as key_file:
                return key_file.read()
        return None

    @property
    def developer_token(self):
        if not self._developer_token:
            self._authenticate()
        return self._developer_token

    @property
    def user_token(self):
        if not self._user_token:
            raise Exception("Apple Music user token not set")
        return self._user_token

    def _authenticate(self):
        if not self._developer_token:
            self._developer_token = self._generate_developer_token()
        return self._developer_token

    def _generate_developer_token(self):
        if not (self.key_id and self.team_id and self._private_key):
            raise Exception(
                "Apple Music credentials missing: APPLE_MUSIC_KEY_ID, "
                "APPLE_MUSIC_TEAM_ID and APPLE_MUSIC_PRIVATE_KEY (or "
                "APPLE_MUSIC_PRIVATE_KEY_PATH) are required"
            )

        issued_at = int(time.time())
        expiration = issued_at + self.DEVELOPER_TOKEN_LIFETIME
        headers = {"kid": self.key_id}
        payload = {"iss": self.team_id, "iat": issued_at, "exp": expiration}

        logger.info(f"Generating Apple Music developer token for team {self.team_id}")
        return jwt.encode(
            payload, self._private_key, algorithm="ES256", headers=headers
        )

    def _developer_headers(self):
        return {
            "Authorization": "Bearer " + self.developer_token,
            "Content-Type": "application/json",
        }

    def _user_headers(self):
        headers = self._developer_headers()
        headers["Music-User-Token"] = self.user_token
        return headers

    #
    # Playlist management
    #
    def ensure_playlist(self, name: str = None, description: str = None) -> str:
        """Return the playlist id to use, creating the playlist when it does
        not exist yet. Re-running the sync will not create duplicates."""
        if self.playlist_id:
            return self.playlist_id

        name = name or self.playlist_name
        playlist_id = self._find_library_playlist_by_name(name)
        if not playlist_id:
            logger.info(f"Apple Music playlist '{name}' not found, creating it")
            playlist_id = self.create_playlist(name, description=description)

        self.playlist_id = playlist_id
        return self.playlist_id

    def _find_library_playlist_by_name(self, name: str):
        r = requests.get(
            f"{self.API_BASE_URL}/me/playlists",
            headers=self._user_headers(),
            params={"limit": 100},
        )

        if not r.ok:
            logger.warning(
                f"Could not list Apple Music library playlists: HTTP {r.status_code}"
            )
            return None

        for playlist in r.json().get("data", []):
            if playlist.get("attributes", {}).get("name") == name:
                return playlist.get("id")
        return None

    def create_playlist(
        self, name: str, description: str = None, tracks: Optional[List[Item]] = None
    ) -> str:
        logger.info(f"Creating Apple Music playlist '{name}'")

        attributes = {"name": name}
        if description:
            attributes["description"] = description

        body = {"attributes": attributes}
        if tracks:
            body["relationships"] = {
                "tracks": {
                    "data": [{"id": track.id, "type": "songs"} for track in tracks]
                }
            }

        r = requests.post(
            f"{self.API_BASE_URL}/me/playlists",
            json=body,
            headers=self._user_headers(),
        )

        if not r.ok:
            logger.warning(
                f"Error creating Apple Music playlist '{name}': "
                f"HTTP {r.status_code} {r.text}"
            )
            r.raise_for_status()

        playlist = r.json()["data"][0]
        self.playlist_id = playlist["id"]
        logger.info(f"Created Apple Music playlist '{name}' ({self.playlist_id})")
        return self.playlist_id

    def _delete_playlist(self, playlist_id: str):
        r = requests.delete(
            f"{self.API_BASE_URL}/me/playlists/{playlist_id}",
            headers=self._user_headers(),
        )
        if not r.ok:
            logger.warning(
                f"Failed to delete Apple Music playlist {playlist_id}: "
                f"HTTP {r.status_code}"
            )
        else:
            logger.info(f"Deleted Apple Music playlist {playlist_id}")

    #
    # BasePlaylistService implementation
    #
    def get_playlist(self) -> List[Item]:
        result_list = []
        offset = 0
        limit = 100

        while True:
            r = requests.get(
                f"{self.API_BASE_URL}/me/playlists/{self.playlist_id}/tracks",
                headers=self._user_headers(),
                params={"limit": limit, "offset": offset},
            )

            if not r.ok:
                logger.warning(
                    f"Error fetching Apple Music playlist tracks: "
                    f"HTTP {r.status_code} {r.text}"
                )
                r.raise_for_status()

            results = r.json()
            page = results.get("data", [])
            for track in page:
                result_list.append(Item(id=track["id"]))

            if "next" in results and page:
                offset += len(page)
            else:
                break

        return result_list

    def add_playlist_items(self, tracks):
        tracks = list(tracks or [])
        if not tracks:
            logger.info("No new tracks to add to the Apple Music playlist")
            return

        payload = {"data": [{"id": track.id, "type": "songs"} for track in tracks]}
        r = requests.post(
            f"{self.API_BASE_URL}/me/playlists/{self.playlist_id}/tracks",
            json=payload,
            headers=self._user_headers(),
        )

        if not r.ok:
            logger.warning(
                f"Error adding tracks to Apple Music playlist: "
                f"HTTP {r.status_code} {r.text}"
            )
            r.raise_for_status()

        logger.info(
            f"Added {len(tracks)} tracks to Apple Music playlist {self.playlist_id}"
        )

    def remove_playlist_items(self, tracks):
        """Best-effort removal. The Apple Music API does not support deleting
        tracks from a user library playlist; in that case this returns False
        so sync_playlist can recreate the playlist instead."""
        tracks = list(tracks or [])
        if not tracks:
            return True

        payload = {"data": [{"id": track.id, "type": "songs"} for track in tracks]}
        r = requests.delete(
            f"{self.API_BASE_URL}/me/playlists/{self.playlist_id}/tracks",
            json=payload,
            headers=self._user_headers(),
        )

        if r.status_code in (403, 404, 405, 501):
            logger.warning(
                "Apple Music API does not support removing tracks from a "
                f"library playlist (HTTP {r.status_code})"
            )
            return False

        if not r.ok:
            logger.warning(
                f"Error removing tracks from Apple Music playlist: "
                f"HTTP {r.status_code} {r.text}"
            )
            r.raise_for_status()

        logger.info(
            f"Removed {len(tracks)} tracks from Apple Music playlist "
            f"{self.playlist_id}"
        )
        return True

    def get_track(self, track_name: str, from_date: datetime = None):
        logger.info(f"Searching Apple Music catalog for {track_name}")

        r = requests.get(
            f"{self.API_BASE_URL}/catalog/{self.storefront}/search",
            headers=self._developer_headers(),
            params={"term": track_name, "types": "songs", "limit": 5},
        )

        if not r.ok:
            logger.warning(
                f"Error searching Apple Music catalog: HTTP {r.status_code} {r.text}"
            )
            return None

        songs = r.json().get("results", {}).get("songs", {}).get("data", [])
        if not songs:
            logger.warning(f"No Apple Music results for {track_name}")
            return None

        track = songs[0]
        track_id = track["id"]
        release_date = track.get("attributes", {}).get("releaseDate")

        if from_date and release_date:
            try:
                release_date = datetime.strptime(release_date[:10], "%Y-%m-%d")
                if release_date < from_date:
                    logger.info(f"Track {track_name} is older than {from_date}")
                    return None
            except ValueError as e:
                logger.warning(f"Error parsing release date '{release_date}': {e}")

        logger.info(f"Found Apple Music track {track_id} for {track_name}")
        return Item(id=track_id)

    def sync_playlist(self, playlist_data, track_id_list):
        # Convert lists to sets
        set_A = set(playlist_data)
        set_B = set(track_id_list)

        # Items in A but not in B need to get removed
        only_in_A = set_A - set_B
        logger.info(f"Tracks to remove: {only_in_A}")

        # Items in B but not in A need to get added
        only_in_B = set_B - set_A
        logger.info(f"Tracks to add: {only_in_B}")

        if only_in_A:
            removed = self.remove_playlist_items(only_in_A)
            if removed is False:
                # The Apple Music API does not allow deleting individual tracks
                # from library playlists. Recreate the playlist with the desired
                # track list so removals are still applied. This can be disabled
                # with APPLE_MUSIC_RECREATE_ON_REMOVE=false.
                if self._should_recreate_on_removal():
                    logger.info("Recreating Apple Music playlist to apply removals")
                    old_playlist_id = self.playlist_id
                    self.playlist_id = None
                    self.create_playlist(self.playlist_name, tracks=list(set_B))
                    self._delete_playlist(old_playlist_id)
                    return
                logger.warning(
                    "Could not remove tracks from the Apple Music playlist; "
                    "set APPLE_MUSIC_RECREATE_ON_REMOVE=true to recreate the "
                    "playlist instead"
                )

        self.add_playlist_items(only_in_B)

    @staticmethod
    def _should_recreate_on_removal() -> bool:
        return os.getenv("APPLE_MUSIC_RECREATE_ON_REMOVE", "true").lower() in (
            "1",
            "true",
            "yes",
        )
