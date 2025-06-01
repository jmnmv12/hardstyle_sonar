import logging
import requests
import time

from bs4 import BeautifulSoup
from scraper import BaseScraper
from typing import List
from scraper.models import TrackData
from datetime import datetime, timedelta
from utils.utils import web_request

logger = logging.getLogger("hardstyle_watcher.scraper.hardstylecom")


class HardstyleDotCom(BaseScraper):

    BASE_URL = "https://hardstyle.com/en/tracks"

    def _before_from_date(self, date_str: str) -> bool:
        # Convert the date string to a datetime object
        date_obj = datetime.strptime(date_str, "%d.%m.%Y")

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

        for track in track_soup:
            time.sleep(1)
            track_object = TrackData()

            track_node = track.find_all("a", class_="linkTitle")
            track_detail_url = track_node[0].get("href")

            # 1. Extract the release date out of the track details
            print(f"https://hardstyle.com{track_detail_url}")
            response_track_detail = web_request(
                f"https://hardstyle.com{track_detail_url}"
            )
            soup_track_detail = BeautifulSoup(
                response_track_detail.content, "html.parser"
            )
            release_date_str = soup_track_detail.find("span", class_="date").text

            # 2. Exclude track if it's before the from_date
            if self._before_from_date(release_date_str):
                continue

            # 3. Extract track details
            title = track_node[0].get("title")
            mix_type = track_node[1].get("title")
            if "remix" not in mix_type.lower():
                mix_type = ""

            artist = self._extract_artist(track)

            track_object.title = f"{title} {mix_type}" if mix_type else title
            track_object.artist_name = artist

            track_data.append(track_object)

        return track_data

    def fetch_tracks(self) -> List[TrackData]:
        track_data = []
        web = requests.Session()

        logger.info("Fetching tracks...")
        for i in range(1, 5):
            time.sleep(0.5)
            logger.info(f"Fetching tracks, page {i}")

            # 1. Retrieve track list
            try:
                response = web_request(f"{self.BASE_URL}?page={i}&genre=Hardstyle")
            except Exception as e:
                logger.warning("Error fetching tracks. Exiting...")
                raise Exception(f"Error fetching tracks: {e}")

            soup_track_list = BeautifulSoup(response.content, "html.parser")
            track_list = soup_track_list.find_all("div", class_="trackContent")

            # 2. Parse track list
            tracks: List[TrackData] = self._extract_tracks_out_of_list(track_list)
            track_data.extend(tracks)

        # 3. Remove duplicate tracks
        track_data = list(set(track_data))

        logger.info(f"Fetched a total of {len(track_data)} entries from hardstyle.com")

        return track_data
