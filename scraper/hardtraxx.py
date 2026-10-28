import itertools
import logging
import time

from bs4 import BeautifulSoup
from scraper import BaseScraper
from typing import List, Optional, Tuple
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
    # Optional hard cap on the number of pages fetched. None means keep
    # paging until the from_date cutoff or an empty page is reached.
    MAX_PAGES: Optional[int] = None

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
                try:
                    return datetime.strptime(raw, "%Y-%m-%d")
                except ValueError:
                    # Malformed date (e.g. "2026-02-30"): treat it as
                    # missing so a single bad row cannot abort the scrape.
                    return None

        return None

    def _extract_tracks_out_of_list(self, track_soup) -> Tuple[List[TrackData], bool]:
        """
        Parse track rows out of a listing page.

        Returns ``(tracks, reached_cutoff)``. ``reached_cutoff`` is True only
        when a parsed row's release date is older than ``from_date``; rows
        skipped for other reasons (no title link, missing or malformed date)
        do not set it, so they can never stop pagination prematurely.
        """
        track_data = []
        reached_cutoff = False

        for track in track_soup:
            link = track.select_one("a.topictitle")
            if link is None:
                continue

            # 1. Extract the release date out of the track row
            release_date = self._extract_release_date(track)
            if release_date is None:
                logger.warning(
                    "Skipping track without release date: %s",
                    link.get_text(strip=True),
                )
                continue

            # 2. Exclude track if it's before the from_date. The listing is
            #    sorted newest first, so an old row means the date window
            #    has ended; deeper pages only contain older tracks.
            if self._before_from_date(release_date):
                reached_cutoff = True
                continue

            # 3. Extract track details
            artist, title = self._split_artist_title(link.get_text(strip=True))

            track_object = TrackData()
            track_object.title = title
            track_object.artist_name = artist
            track_object.release_date = release_date
            track_object.genre = self._extract_genre(track)

            logger.info(
                "Retrieved track: %s - %s, %s",
                track_object.artist_name,
                track_object.title,
                track_object.release_date,
            )
            track_data.append(track_object)

        return track_data, reached_cutoff

    def _build_page_url(self, page: int) -> str:
        if page == 0:
            return f"{self.BASE_URL}{self.QUERY}"

        return f"{self.BASE_URL}page{page * self.TOPICS_PER_PAGE}.html{self.QUERY}"

    def fetch_tracks(self) -> List[TrackData]:
        track_data = []

        logger.info("Fetching tracks...")
        for page in itertools.count():
            if self.MAX_PAGES is not None and page >= self.MAX_PAGES:
                logger.warning("Reached MAX_PAGES limit (%d). Stopping.", self.MAX_PAGES)
                break

            time.sleep(0.5)
            logger.info("Fetching tracks, page %d", page + 1)

            # 1. Retrieve track list
            try:
                response = web_request(self._build_page_url(page))
            except Exception as e:
                logger.warning("Error fetching tracks: %s", e)
                raise Exception(f"Error fetching tracks: {e}") from e

            soup_track_list = BeautifulSoup(response.content, "html.parser")
            track_list = soup_track_list.select(".htx-topic-row")

            if not track_list:
                logger.warning("No track rows found on page %d. Stopping.", page + 1)
                break

            # 2. Parse track list (results are sorted by release date,
            #    newest first). Stop paging only when a parsed row's date
            #    actually fell outside the from_date window or the site has
            #    no more rows; skipped/malformed rows must never cut the
            #    window short.
            tracks, reached_cutoff = self._extract_tracks_out_of_list(track_list)
            track_data.extend(tracks)

            if reached_cutoff:
                break

        # 3. Remove duplicate tracks
        track_data = list(set(track_data))

        logger.info("Fetched a total of %d entries from hardtraxx.com", len(track_data))

        return track_data
