import logging
import re
import time

from bs4 import BeautifulSoup
from scraper import BaseScraper
from typing import List
from scraper.models import Genre, TrackData
from datetime import datetime
from utils.utils import web_request

logger = logging.getLogger("hardstyle_watcher.scraper.hardtraxx")


class HardTraxx(BaseScraper):
    """https://hardtraxx.com/livesets/?tab=event&playable=1"""

    BASE_URL = "https://hardtraxx.com/livesets/"

    # The site sits behind a Cloudflare challenge for browser user agents,
    # a crawler-like user agent gets through.
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; "
        "+http://www.google.com/bot.html)"
    }

    # Matches youtube urls of the form watch?v=, youtu.be/, embed/,
    # shorts/ and live/ followed by an 11 character video id
    YOUTUBE_ID_PATTERN = re.compile(
        r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)"
        r"|youtu\.be/)(?P<video_id>[A-Za-z0-9_-]{11})"
    )

    GENRE_MAP = {
        "hardstyle": Genre.Hardstyle,
        "hs": Genre.Hardstyle,
        "hardcore": Genre.Hardcore,
        "hc": Genre.Hardcore,
    }

    def _before_from_date(self, date_obj: datetime) -> bool:
        # Check if the date is before from_date
        return date_obj < self.from_date

    @classmethod
    def _extract_youtube_video_id(cls, soup) -> str:
        # 1. Prefer an explicit link to the youtube video
        for anchor in soup.find_all("a", href=True):
            match = cls.YOUTUBE_ID_PATTERN.search(anchor["href"])
            if match:
                return match.group("video_id")

        # 2. Fall back to the first youtube url found anywhere in the page
        match = cls.YOUTUBE_ID_PATTERN.search(str(soup))
        if match:
            return match.group("video_id")

        return None

    def _parse_genre(self, row) -> Genre:
        genre_mark = row.find("span", class_="htx-genre-mark")
        if genre_mark is None:
            return Genre.Unknown

        # The mark carries the full genre name in its title attribute
        # and an abbreviation as text (e.g. title="Hardstyle", text="HS")
        for value in (genre_mark.get("title"), genre_mark.get_text(strip=True)):
            if value:
                genre = self.GENRE_MAP.get(value.strip().lower())
                if genre is not None:
                    return genre

        return Genre.Unknown

    def _parse_liveset_rows(self, soup) -> List[dict]:
        rows = []
        for row in soup.find_all("dl", class_="htx-topic-row"):
            link = row.find("a", class_="topictitle")
            if link is None or not link.get("href"):
                continue

            posted_date = None
            time_node = row.find("time", attrs={"datetime": True})
            if time_node is not None:
                try:
                    posted_date = datetime.fromisoformat(time_node["datetime"])
                except ValueError as e:
                    logger.warning(f"Error parsing liveset date: {e}")

            rows.append(
                {
                    "title": link.get("title") or link.get_text(strip=True),
                    "url": link["href"],
                    "date": posted_date,
                    "genre": self._parse_genre(row),
                }
            )

        return rows

    def fetch_tracks(self) -> List[TrackData]:
        track_data = []
        logger.info("Fetching livesets...")

        # 1. Retrieve the latest playable event livesets
        try:
            response = web_request(
                f"{self.BASE_URL}?tab=event&playable=1", headers=self.HEADERS
            )
        except Exception as e:
            logger.warning("Error fetching livesets. Exiting...")
            raise Exception(f"Error fetching livesets: {e}")

        soup = BeautifulSoup(response.content, "html.parser")
        rows = self._parse_liveset_rows(soup)
        logger.info(f"Parsed {len(rows)} liveset entries from hardtraxx.com")

        # 2. For each recent liveset, fetch the details page and
        #    extract the youtube video of the set
        for row in rows:
            if row["date"] is not None and self._before_from_date(row["date"]):
                continue

            try:
                time.sleep(0.5)
                detail_response = web_request(row["url"], headers=self.HEADERS)
            except Exception as e:
                logger.warning(f"Error fetching liveset {row['url']}: {e}")
                continue

            detail_soup = BeautifulSoup(detail_response.content, "html.parser")
            youtube_video_id = self._extract_youtube_video_id(detail_soup)

            # 3. Skip livesets that do not have a youtube video
            if youtube_video_id is None:
                logger.info(f"Skipping liveset without youtube video: {row['title']}")
                continue

            logger.info(
                f"Retrieved liveset: {row['title']} ({youtube_video_id})"
            )
            track_data.append(
                TrackData(
                    track_name=row["title"],
                    artist_name="",
                    track_date=row["date"],
                    genre=row["genre"],
                    youtube_video_id=youtube_video_id,
                )
            )

        # 4. Remove duplicate livesets
        track_data = list(set(track_data))

        logger.info(
            f"Fetched a total of {len(track_data)} livesets from hardtraxx.com"
        )

        return track_data
