import logging
import time

from bs4 import BeautifulSoup
from scraper import BaseScraper
from typing import List
from scraper.models import TrackData
from scraper.models.track_data import Genre
from datetime import datetime
from utils.utils import web_request

logger = logging.getLogger("hardstyle_watcher.scraper.hardtraxx")


class HardTraxx(BaseScraper):
    """
    Release provider for https://hardtraxx.com/tracks/?tab=released&sort=date

    NOTE: this provider is intentionally NOT wired into the main sync loop
    (main.py). It is kept available as an alternative to the hardstyle.com
    provider and can be activated manually when needed.
    """

    BASE_URL = "https://hardtraxx.com/tracks/"
    QUERY = "?tab=released&sort=date"
    TOPICS_PER_PAGE = 30
    MAX_PAGES = 2

    GENRE_MAP = {
        "hardstyle": Genre.Hardstyle,
        "hardcore": Genre.Hardcore,
    }

    def _before_from_date(self, date_obj: datetime) -> bool:
        # Check if the date is before from_date
        return date_obj < self.from_date

    def _split_artist_title(self, raw_title: str):
        # Topics on hardtraxx.com are formatted as "Artist - Title"
        if " - " in raw_title:
            artist, title = raw_title.split(" - ", 1)
            return artist.strip(), title.strip()

        return "", raw_title.strip()

    def _extract_genre(self, track):
        genre_mark = track.select_one(".htx-genre-mark")

        if genre_mark is not None:
            genre_title = (genre_mark.get("title") or "").strip().lower()
            return self.GENRE_MAP.get(genre_title, Genre.Unknown)

        return Genre.Unknown

    def _extract_release_date(self, track):
        # The release date is a date-only <time datetime="YYYY-MM-DD">
        # inside the topic-poster section. Do not confuse it with the
        # full ISO last-post timestamp inside the .lastpost column.
        candidates = []
        scoped = track.select_one(".htx-topic-poster time") or track.select_one("time")
        if scoped is not None:
            candidates.append(scoped)
        candidates.extend(track.find_all("time"))

        for time_el in candidates:
            raw = (time_el.get("datetime") or "").strip()
            if len(raw) == 10:
                return datetime.strptime(raw, "%Y-%m-%d")

        return None

    def _extract_tracks_out_of_list(self, track_soup):
        track_data = []

        for track in track_soup:
            link = track.select_one("a.topictitle")
            if link is None:
                continue

            # 1. Extract the release date out of the track row
            release_date = self._extract_release_date(track)
            if release_date is None:
                logger.warning(
                    f"Skipping track without release date: {link.get_text(strip=True)}"
                )
                continue

            # 2. Exclude track if it's before the from_date
            if self._before_from_date(release_date):
                continue

            # 3. Extract track details
            artist, title = self._split_artist_title(link.get_text(strip=True))

            track_object = TrackData()
            track_object.title = title
            track_object.artist_name = artist
            track_object.release_date = release_date
            track_object.genre = self._extract_genre(track)

            logger.info(
                f"Retrieved track: {track_object.artist_name} - "
                f"{track_object.title}, {track_object.release_date}"
            )
            track_data.append(track_object)

        return track_data

    def _build_page_url(self, page: int) -> str:
        if page == 0:
            return f"{self.BASE_URL}{self.QUERY}"

        return f"{self.BASE_URL}page{page * self.TOPICS_PER_PAGE}.html{self.QUERY}"

    def fetch_tracks(self) -> List[TrackData]:
        track_data = []

        logger.info("Fetching tracks...")
        for page in range(self.MAX_PAGES):
            time.sleep(0.5)
            logger.info(f"Fetching tracks, page {page + 1}")

            # 1. Retrieve track list
            try:
                response = web_request(self._build_page_url(page))
            except Exception as e:
                logger.warning("Error fetching tracks. Exiting...")
                raise Exception(f"Error fetching tracks: {e}")

            soup_track_list = BeautifulSoup(response.content, "html.parser")
            track_list = soup_track_list.select(".htx-topic-row")

            if not track_list:
                logger.warning(f"No track rows found on page {page + 1}. Stopping.")
                break

            # 2. Parse track list (results are sorted by release date,
            #    newest first). If any row on this page fell outside the
            #    from_date window, deeper pages only contain older tracks.
            tracks: List[TrackData] = self._extract_tracks_out_of_list(track_list)
            track_data.extend(tracks)

            if len(tracks) < len(track_list):
                break

        # 3. Remove duplicate tracks
        track_data = list(set(track_data))

        logger.info(f"Fetched a total of {len(track_data)} entries from hardtraxx.com")

        return track_data
