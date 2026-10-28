import logging
import sys
import os

from scraper import HardstyleDotCom, ReleaseHardstyle
from playlist import Spotify, AppleMusic
from playlist.models import Item
from datetime import datetime, timedelta
from dotenv import load_dotenv

current_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

logging.basicConfig(
    level=logging.NOTSET,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs/hardstyle_watcher_{current_datetime}.log"),
    ],
)
logger = logging.getLogger("hardstyle_watcher.main")
load_dotenv()


def sync():
    logger.info("Starting sync")

    #
    # 1. Init Scraper
    # scraper = HardstyleDotCom(from_date=datetime.now() - timedelta(days=7))
    scraper = ReleaseHardstyle(from_date=datetime.now() - timedelta(days=2))

    #
    # 2. Fetch track list
    track_list = scraper.fetch_tracks()

    #
    # 3. Init Playlist Service
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    spotify = Spotify(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://localhost:8080",
        playlist_id=os.getenv("SPOTIFY_PLAYLIST_ID"),
    )

    #
    # 4. Fetch playlist
    playlist_data = spotify.get_playlist()

    #
    # 5. For each fetched track, retrieve the Spotify URI
    new_track_list = []
    for track in track_list:
        if track.spotify_uri:
            new_track_list.append(Item(id=track.spotify_uri))
            continue
        else:
            track_id = spotify.get_track(
                f"track:{track.title}" + " " + f"artist:{track.artist_name}",
                from_date=datetime.now() - timedelta(days=7),
            )
            if track_id:
                new_track_list.append(track_id)
            else:
                logger.warning(f"Track not found: {track}")

    #
    # 6. Compare the fetched tracks with the playlist
    #   and remove tracks that are older than from_date
    #   and add new tracks
    spotify.sync_playlist(playlist_data, new_track_list)

    #
    # 7. Create and sync the playlist on Apple Music as well
    _sync_apple_music(track_list)


def _sync_apple_music(track_list):
    """Create and sync the playlist on Apple Music, mirroring the Spotify
    playlist. Skipped (with a warning) when Apple Music credentials are not
    configured, and never breaks the Spotify sync when it fails."""
    logger.info("Starting Apple Music sync")

    required_settings = (
        "APPLE_MUSIC_KEY_ID",
        "APPLE_MUSIC_TEAM_ID",
        "APPLE_MUSIC_USER_TOKEN",
    )
    if not all(os.getenv(setting) for setting in required_settings) or not (
        os.getenv("APPLE_MUSIC_PRIVATE_KEY")
        or os.getenv("APPLE_MUSIC_PRIVATE_KEY_PATH")
    ):
        logger.warning(
            "Apple Music credentials not configured, skipping Apple Music sync"
        )
        return

    apple_music = AppleMusic(
        key_id=os.getenv("APPLE_MUSIC_KEY_ID"),
        team_id=os.getenv("APPLE_MUSIC_TEAM_ID"),
        private_key=os.getenv("APPLE_MUSIC_PRIVATE_KEY"),
        private_key_path=os.getenv("APPLE_MUSIC_PRIVATE_KEY_PATH"),
        user_token=os.getenv("APPLE_MUSIC_USER_TOKEN"),
        playlist_id=os.getenv("APPLE_MUSIC_PLAYLIST_ID"),
        playlist_name=os.getenv("APPLE_MUSIC_PLAYLIST_NAME", "Hardstyle Sonar"),
        storefront=os.getenv("APPLE_MUSIC_STOREFRONT", "nl"),
    )

    try:
        #
        # Create the playlist when it does not exist yet (an existing playlist
        # with the same name is reused to avoid duplicates)
        apple_music.ensure_playlist()
        playlist_data = apple_music.get_playlist()
    except Exception as e:
        logger.warning(f"Could not open the Apple Music playlist: {e}")
        return

    apple_music_track_list = []
    for track in track_list:
        track_id = apple_music.get_track(
            f"{track.title} {track.artist_name}",
            from_date=datetime.now() - timedelta(days=7),
        )
        if track_id:
            apple_music_track_list.append(track_id)
        else:
            logger.warning(f"Track not found on Apple Music: {track}")

    apple_music.sync_playlist(playlist_data, apple_music_track_list)
    logger.info("Apple Music sync finished")


if __name__ == "__main__":
    sync()
