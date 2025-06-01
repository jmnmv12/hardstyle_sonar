import logging
import sys
import os

from scraper import HardstyleDotCom, ReleaseHardstyle
from playlist import Spotify
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


if __name__ == "__main__":
    sync()
