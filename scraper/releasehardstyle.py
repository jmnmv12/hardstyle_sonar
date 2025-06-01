import logging
import requests
import time

from bs4 import BeautifulSoup
from scraper import BaseScraper
from typing import List
from scraper.models import TrackData
from datetime import datetime, timedelta
from utils.utils import web_request

logger = logging.getLogger("hardstyle_watcher.scraper.releasehardstyle")


class ReleaseHardstyle(BaseScraper):
    """https://releasehardstyle.nl/releases/"""

    BASE_URL = "https://releasehardstyle.nl/releases/"

    def _before_from_date(self, date_obj: datetime) -> bool:
        # Check if the date is before from_date
        return date_obj < self.from_date

    def _extract_artist(self, track):
        node_1 = track.find("span", class_="artists").find("a", class_="highlight")

        if node_1 is not None:
            return node_1.get("title")

        return track.find("span", class_="artists").text

    def _extract_tracks_out_of_list(self, track_soup):
        track_data = []
        web = requests.Session()
        print(len(track_soup))
        for track in track_soup:
            time.sleep(1)
            track_object = TrackData()

            track_id = track.get("targetid")

            spotify_uri = track.find(id="releasetracker-a").get("href").split("/")[-1]

            # 1. Extract the release date out of the track details
            response_track_detail = web_request(
                f"https://releasehardstyle.nl/release/{track_id}/"
            )
            soup_track_detail = BeautifulSoup(
                response_track_detail.content, "html.parser"
            )

            text_content = soup_track_detail.find(
                "div", class_="releasetracker_details-info_container-inner"
            ).get_text(separator="\n")

            # Extract the title and release date using simple string operations
            lines = text_content.split("\n")
            title_line = next(line for line in lines if "Title:" in line)
            release_date_line = next(line for line in lines if "Release date:" in line)

            # Clean up the extracted lines to get the desired values
            title = title_line.replace("Title:", "").strip()
            release_date = release_date_line.replace("Release date:", "").strip()

            # 2. Exclude track if it's before the from_date
            track_object.spotify_uri = spotify_uri
            track_object.title = title
            track_object.artist_name = ""
            track_object.release_date = datetime.strptime(release_date, "%d %b %Y")

            if self._before_from_date(track_object.release_date):
                break

            logger.info(
                f"Retrieved track: {track_object.title}, {track_object.release_date}"
            )
            track_data.append(track_object)
        return track_data

    def fetch_tracks(self) -> List[TrackData]:
        track_data = []
        logger.info("Fetching tracks...")
        # 1. Retrieve track list
        try:
            response = web_request(self.BASE_URL)
        except Exception as e:
            logger.warning("Error fetching tracks. Exiting...")
            raise Exception(f"Error fetching tracks: {e}")

        soup_track_list = BeautifulSoup(response.content, "html.parser")
        track_divs = soup_track_list.find_all(
            "div", class_="releasetracker-list-container"
        )

        track_list = track_divs[1].find_all("div", class_="releasetracker-list-entry")

        # 2. Parse track list
        tracks: List[TrackData] = self._extract_tracks_out_of_list(track_list)
        track_data.extend(tracks)

        # 3. Remove duplicate tracks
        track_data = list(set(track_data))

        logger.info(
            f"Fetched a total of {len(track_data)} entries from releasehardstyle.nl"
        )

        return track_data
