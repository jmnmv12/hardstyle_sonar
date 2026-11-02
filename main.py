import logging
import sys
import os

from scraper import HardTraxx, HardstyleDotCom, ReleaseHardstyle
from playlist import Spotify, YouTube
from playlist.models import Item
from datetime import datetime, timedelta
from dotenv import load_dotenv

current_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
os.makedirs("logs", exist_ok=True)

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


def sync_livesets():
    logger.info("Starting livesets sync")

    #
    # 1. Init livesets scraper
    scraper = HardTraxx(from_date=datetime.now() - timedelta(days=7))

    #
    # 2. Fetch the latest livesets that have a youtube video
    livesets = scraper.fetch_tracks()

    if not livesets:
        logger.info("No livesets with a youtube video found")
        return

    #
    # 3. Init Playlist Service
    youtube = YouTube(
        client_id=os.getenv("YOUTUBE_CLIENT_ID"),
        client_secret=os.getenv("YOUTUBE_CLIENT_SECRET"),
        refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN"),
        playlist_id=os.getenv("YOUTUBE_PLAYLIST_ID"),
        playlist_title=os.getenv("YOUTUBE_PLAYLIST_TITLE", "Hardstyle Sonar Livesets"),
    )

    #
    # 4. Reuse the configured playlist, or look it up by title
    #    and create it when it does not exist yet
    youtube.ensure_playlist()

    #
    # 5. Fetch the current contents of the playlist
    playlist_data = youtube.get_playlist()

    #
    # 6. Map the livesets to playlist items using their youtube video id
    liveset_items = [Item(id=liveset.youtube_video_id) for liveset in livesets]

    #
    # 7. Add the new livesets and remove the ones that have been in the
    #    playlist for at least 30 days
    youtube.sync_playlist(playlist_data, liveset_items)


if __name__ == "__main__":
    try:
        sync()
    except Exception as e:
        logger.error(f"Spotify sync failed: {e}")

    try:
        sync_livesets()
    except Exception as e:
        logger.error(f"YouTube livesets sync failed: {e}")
