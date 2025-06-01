import webbrowser
import requests
import base64
import os
import logging

from datetime import datetime
from playlist import BasePlaylistService
from urllib.parse import urlencode
from dotenv import load_dotenv
from playlist.models import Item

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("hardstyle_watcher.playlist.spotifyapi")
load_dotenv()


class SpotifyAPI(BasePlaylistService):

    client_id: str
    client_secret: str
    redirect_uri: str
    _access_token: str
    _refresh_token: str
    _authorization_code: str

    def __init__(
        self,
        client_id: str = None,
        client_secret: str = None,
        authorization_code: str = None,
        redirect_uri: str = None,
        playlist_id: str = None,
    ):
        super().__init__(playlist_id)
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self._authorization_code = authorization_code

        # TODO Handle refresh token better, store the
        # expiration time and refresh the token when needed
        self._refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        self._access_token = os.getenv("SPOTIFY_ACCESS_TOKEN")
        self._refresh_authentication()

    @property
    def authorization_code(self):
        if not self._authorization_code:
            raise Exception("Authorization code not set")
        return self._authorization_code

    @property
    def access_token(self):
        if not self._access_token:
            self._authenticate()
        return self._access_token

    # TODO Remove this, listen to the callback url and
    # extract the code from the url
    def authorize(self):
        auth_headers = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": "user-read-private playlist-modify-private playlist-read-collaborative playlist-modify-private playlist-modify-public",
        }

        webbrowser.open(
            "https://accounts.spotify.com/authorize?" + urlencode(auth_headers)
        )

    def _authenticate(self):
        encoded_credentials = base64.b64encode(
            self.client_id.encode() + b":" + self.client_secret.encode()
        ).decode("utf-8")

        token_headers = {
            "Authorization": "Basic " + encoded_credentials,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        token_data = {
            "grant_type": "authorization_code",
            "code": self.authorization_code,
            "redirect_uri": "http://localhost:8080",
        }

        r = requests.post(
            "https://accounts.spotify.com/api/token",
            data=token_data,
            headers=token_headers,
        )

        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.warning(f"Error authenticating with Spotify: {e}")
            raise e

        results = r.json()

        self._access_token = results["access_token"]
        self._refresh_token = results["refresh_token"]

    def _refresh_authentication(self):
        encoded_credentials = base64.b64encode(
            self.client_id.encode() + b":" + self.client_secret.encode()
        ).decode("utf-8")

        token_headers = {
            "Authorization": "Basic " + encoded_credentials,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }

        r = requests.post(
            "https://accounts.spotify.com/api/token",
            data=token_data,
            headers=token_headers,
        )
        logger.info(f"Refreshing Spotify authentication {token_data}")
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.warning(f"Error authenticating with Spotify: {e}")
            raise e

        results = r.json()

        self._access_token = results["access_token"]

    def get_playlist(self):
        def _parse_response(response):
            result_list = []
            for item in response["items"]:
                track = item["track"]
                uri = track["uri"]
                result_list.append(Item(id=uri))

            return result_list

        user_headers = {
            "Authorization": "Bearer " + self.access_token,
            "Content-Type": "application/json",
        }

        query_params = {
            "fields": "items(added_at,track(album(release_date),uri))",
        }

        r = requests.get(
            f"https://api.spotify.com/v1/playlists/{self.playlist_id}/tracks?"
            + urlencode(query_params),
            headers=user_headers,
        )

        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.warning(f"Error authenticating with Spotify: {e}")
            raise e

        results = r.json()

        return _parse_response(results)

    def remove_playlist_items(self, tracks: list[Item]):
        def _build_payload(tracks: list[Item]):
            track_uri_list = []
            for track in tracks:
                track_uri_list.append({"uri": track.id})

            return track_uri_list

        user_headers = {
            "Authorization": "Bearer " + self.access_token,
            "Content-Type": "application/json",
        }

        payload = {"tracks": _build_payload(tracks)}

        response = requests.delete(
            f"https://api.spotify.com/v1/playlists/{self.playlist_id}/tracks",
            json=payload,
            headers=user_headers,
        )

    def add_playlist_items(self, tracks: list[Item]):
        def _build_payload(tracks: list[Item]):
            track_uri_list = []
            for track in tracks:
                track_uri_list.append(track.id)

            return track_uri_list

        user_headers = {
            "Authorization": "Bearer " + self.access_token,
            "Content-Type": "application/json",
        }

        req_body = {"uris": ["2jE9r0cUSWoOkFWrDQVU3d"], "position": 0}
        print(req_body)
        tracks_response = requests.post(
            f"https://api.spotify.com/v1/playlists/{self.playlist_id}/tracks",
            json=req_body,
            headers=user_headers,
        )
        print(tracks_response.json())

    def get_track(self, track_name: str, from_date: datetime = None):
        logger.info(f"Gathering track uri for {track_name}")

        def make_request():
            user_headers = {
                "Authorization": "Bearer " + self.access_token,
                "Content-Type": "application/json",
            }

            user_params = {
                "limit": 5,
                "type": "track",
                "market": "NL",
            }

            r = requests.get(
                "https://api.spotify.com/v1/search?q=" + track_name,
                params=user_params,
                headers=user_headers,
            )
            return r

        # First attempt to make the request
        r = make_request()
        self._refresh_authentication()

        # Check if the request failed due to an unauthorized error
        if r.status_code == 401:
            logger.info("Access token expired, refreshing token...")
            self._refresh_authentication()  # Refresh the token

            # Retry the request with the new access token
            r = make_request()

        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.warning(f"Error authenticating with Spotify: {e}")
            raise e

        results = r.json()
        logger.info(f"Results: {results}")

        try:
            track_uri = results["tracks"]["items"][0]["uri"]
            release_date = results["tracks"]["items"][0]["album"]["release_date"]
            # Try to retrieve year-month-day release date
            try:
                release_date = datetime.strptime(release_date, "%Y-%m-%d")
                if release_date < from_date:
                    logger.info(f"Track {track_name} is older than {from_date}")
                    return None
            except ValueError as e:
                logger.warning(f"Error parsing release date: {e}")
        except Exception as e:
            logger.warning(f"Failed to gather track uri for {track_name}: {e}")
            return None
        logger.info(f"Gathered track uri {track_uri} for {track_name}")

        return Item(id=track_uri)

    def sync_playlist(self, playlist_data, track_id_list):
        # Convert lists to sets
        set_A = set(playlist_data)
        set_B = set(track_id_list)

        # Items in A but not in B
        # Need to get removed
        only_in_A = set_A - set_B
        logger.info(f"Tracks to remove: {only_in_A}")

        # Items in B but not in A
        # Need to get added
        only_in_B = set_B - set_A
        logger.info(f"Tracks to add: {only_in_B}")

        # Remove tracks
        self.remove_playlist_items(only_in_A)

        # Add tracks
        self.add_playlist_items(only_in_B)
