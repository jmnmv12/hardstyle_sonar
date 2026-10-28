import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from scraper import HardTraxx
from scraper.models.track_data import Genre


REPO_ROOT = Path(__file__).resolve().parents[1]


def make_row(title: str, date_iso: str, genre: str = "Hardstyle") -> str:
    """Build a track row matching the hardtraxx.com markup."""
    return f"""
    <dl class="row-item htx-topic-row">
      <dt class="htx-topic-main">
        <div class="list-inner">
          <div class="htx-topic-title">
            <a class="topictitle htx-topic-link"
               href="https://hardtraxx.com/tracks/some-track-t123.html"
               title="{title}">{title}</a>
          </div>
          <div class="topic-poster htx-topic-poster">
            <span class="htx-genre-mark" title="{genre}">HS</span>
            <span class="htx-topic-week">Out today</span>
            <time class="num" datetime="{date_iso}">Fri 2 Oct</time>
          </div>
        </div>
      </dt>
      <dd class="lastpost htx-topic-last">
        <time datetime="2026-09-30T19:56:38+00:00">30 Sep 2026 21:56</time>
      </dd>
    </dl>
    """


def rows_soup(*rows: str) -> BeautifulSoup:
    return BeautifulSoup("".join(rows), "html.parser")


@pytest.fixture
def scraper() -> HardTraxx:
    return HardTraxx(from_date=datetime(2026, 9, 25))


class TestSplitArtistTitle:
    def test_simple(self, scraper):
        assert scraper._split_artist_title("Demi Kanon & Caelum - Paralyzed") == (
            "Demi Kanon & Caelum",
            "Paralyzed",
        )

    def test_title_containing_dash(self, scraper):
        assert scraper._split_artist_title("Frontliner - Running, Running - Edit") == (
            "Frontliner",
            "Running, Running - Edit",
        )

    def test_no_artist(self, scraper):
        assert scraper._split_artist_title("Just A Title") == ("", "Just A Title")


class TestExtractReleaseDate:
    def test_prefers_release_date_over_lastpost_time(self, scraper):
        soup = rows_soup(make_row("Artist - Title", "2026-10-01"))
        row = soup.select_one(".htx-topic-row")
        assert scraper._extract_release_date(row) == datetime(2026, 10, 1)

    def test_missing_date_returns_none(self, scraper):
        html = make_row("Artist - Title", "2026-10-01").replace(
            '<time class="num" datetime="2026-10-01">Fri 2 Oct</time>', ""
        )
        soup = rows_soup(html)
        row = soup.select_one(".htx-topic-row")
        assert scraper._extract_release_date(row) is None

    def test_malformed_date_returns_none(self, scraper):
        # 2026-02-30 looks well-formed but is an invalid calendar date;
        # strptime raises ValueError and must be handled gracefully.
        soup = rows_soup(make_row("Artist - Title", "2026-02-30"))
        row = soup.select_one(".htx-topic-row")
        assert scraper._extract_release_date(row) is None


class TestExtractGenre:
    def test_hardstyle(self, scraper):
        row = rows_soup(make_row("A - B", "2026-10-01")).select_one(".htx-topic-row")
        assert scraper._extract_genre(row) == Genre.Hardstyle

    def test_hardcore(self, scraper):
        row = rows_soup(make_row("A - B", "2026-10-01", genre="Hardcore")).select_one(
            ".htx-topic-row"
        )
        assert scraper._extract_genre(row) == Genre.Hardcore

    def test_unknown(self, scraper):
        row = rows_soup(make_row("A - B", "2026-10-01", genre="Uptempo")).select_one(
            ".htx-topic-row"
        )
        assert scraper._extract_genre(row) == Genre.Unknown


class TestExtractTracks:
    def test_parses_track_fields(self, scraper):
        soup = rows_soup(
            make_row("Demi Kanon & Caelum - Paralyzed", "2026-10-02"),
            make_row("Frontliner - Running, Running Running (Edit)", "2026-09-26"),
        )
        tracks, reached_cutoff = scraper._extract_tracks_out_of_list(
            soup.select(".htx-topic-row")
        )

        assert len(tracks) == 2
        assert reached_cutoff is False
        by_title = {t.title: t for t in tracks}

        paralyzed = by_title["Paralyzed"]
        assert paralyzed.artist_name == "Demi Kanon & Caelum"
        assert paralyzed.release_date == datetime(2026, 10, 2)
        assert paralyzed.genre == Genre.Hardstyle

        running = by_title["Running, Running Running (Edit)"]
        assert running.artist_name == "Frontliner"
        assert running.release_date == datetime(2026, 9, 26)

    def test_excludes_tracks_older_than_from_date(self, scraper):
        soup = rows_soup(
            make_row("A - New Track", "2026-10-02"),
            make_row("B - Old Track", "2026-09-24"),
        )
        tracks, reached_cutoff = scraper._extract_tracks_out_of_list(
            soup.select(".htx-topic-row")
        )

        assert [t.title for t in tracks] == ["New Track"]
        assert reached_cutoff is True

    def test_skips_rows_without_title_link(self, scraper):
        soup = rows_soup(make_row("A - B", "2026-10-01"))
        extra = BeautifulSoup("<dl class=\"htx-topic-row\"></dl>", "html.parser")
        rows = soup.select(".htx-topic-row") + extra.select("dl")

        tracks, reached_cutoff = scraper._extract_tracks_out_of_list(rows)
        assert len(tracks) == 1
        assert reached_cutoff is False


class TestFetchTracks:
    def _fake_response(self, rows_html: str):
        return SimpleNamespace(content=rows_html.encode("utf-8"))

    def test_fetch_tracks_returns_recent_tracks_only(self, scraper):
        page1 = (
            '<!DOCTYPE html><html><body>'
            + make_row("A - Track One", "2026-10-02")
            + make_row("B - Track Two", "2026-09-30")
            + make_row("C - Old Track", "2026-09-20")
            + "</body></html>"
        )
        page2 = "<html><body></body></html>"

        responses = [self._fake_response(page1), self._fake_response(page2)]

        with patch("scraper.hardtraxx.web_request", side_effect=responses) as mock_req, patch(
            "scraper.hardtraxx.time.sleep"
        ):
            tracks = scraper.fetch_tracks()

        titles = sorted(t.title for t in tracks)
        assert titles == ["Track One", "Track Two"]

        # First page uses the plain released/sort=url, next pages page{offset}.html
        first_call_url = mock_req.call_args_list[0][0][0]
        assert first_call_url == "https://hardtraxx.com/tracks/?tab=released&sort=date"

    def test_fetch_tracks_stops_when_page_contains_old_tracks(self, scraper):
        page1 = (
            '<!DOCTYPE html><html><body>'
            + make_row("A - Fresh", "2026-10-02")
            + make_row("B - Ancient", "2026-01-01")
            + "</body></html>"
        )

        with patch(
            "scraper.hardtraxx.web_request",
            side_effect=[self._fake_response(page1)],
        ) as mock_req, patch("scraper.hardtraxx.time.sleep"):
            tracks = scraper.fetch_tracks()

        assert [t.title for t in tracks] == ["Fresh"]
        # Only one page requested because an old track ended the window
        assert mock_req.call_count == 1

    def test_fetch_tracks_deduplicates(self, scraper):
        page1 = (
            '<!DOCTYPE html><html><body>'
            + make_row("A - Same Track", "2026-10-02")
            + make_row("A - Same Track", "2026-10-02")
            + "</body></html>"
        )
        page2 = "<html><body></body></html>"

        with patch(
            "scraper.hardtraxx.web_request",
            side_effect=[self._fake_response(page1), self._fake_response(page2)],
        ), patch("scraper.hardtraxx.time.sleep"):
            tracks = scraper.fetch_tracks()

        assert len(tracks) == 1

    def test_fetch_tracks_continues_past_malformed_rows(self, scraper):
        page1 = (
            '<!DOCTYPE html><html><body>'
            + '<dl class="htx-topic-row"><dd>broken row</dd></dl>'
            + make_row("A - Track One", "2026-10-02")
            + "</body></html>"
        )
        page2 = (
            '<!DOCTYPE html><html><body>'
            + make_row("B - Track Two", "2026-09-30")
            + "</body></html>"
        )
        page3 = "<html><body></body></html>"

        with patch(
            "scraper.hardtraxx.web_request",
            side_effect=[
                self._fake_response(page1),
                self._fake_response(page2),
                self._fake_response(page3),
            ],
        ) as mock_req, patch("scraper.hardtraxx.time.sleep"):
            tracks = scraper.fetch_tracks()

        titles = sorted(t.title for t in tracks)
        assert titles == ["Track One", "Track Two"]
        # A malformed row on page 1 must not stop pagination
        assert mock_req.call_count == 3

    def test_fetch_tracks_fetches_more_than_two_pages(self, scraper):
        pages = []
        for number, date_iso in enumerate(
            ["2026-10-02", "2026-09-30", "2026-09-28"], start=1
        ):
            pages.append(
                '<!DOCTYPE html><html><body>'
                + make_row(f"Artist {number} - Track {number}", date_iso)
                + "</body></html>"
            )
        pages.append("<html><body></body></html>")

        with patch(
            "scraper.hardtraxx.web_request",
            side_effect=[self._fake_response(page) for page in pages],
        ) as mock_req, patch("scraper.hardtraxx.time.sleep"):
            tracks = scraper.fetch_tracks()

        titles = sorted(t.title for t in tracks)
        assert titles == ["Track 1", "Track 2", "Track 3"]
        assert mock_req.call_count == 4

    def test_fetch_tracks_stops_at_max_pages_override(self):
        scraper = HardTraxx(from_date=datetime(2026, 9, 25))
        scraper.MAX_PAGES = 1

        page1 = (
            '<!DOCTYPE html><html><body>'
            + make_row("A - Track One", "2026-10-02")
            + "</body></html>"
        )

        with patch(
            "scraper.hardtraxx.web_request",
            side_effect=[self._fake_response(page1), self._fake_response(page1)],
        ) as mock_req, patch("scraper.hardtraxx.time.sleep"):
            tracks = scraper.fetch_tracks()

        assert [t.title for t in tracks] == ["Track One"]
        assert mock_req.call_count == 1

    def test_fetch_tracks_wraps_request_errors(self, scraper):
        with patch(
            "scraper.hardtraxx.web_request", side_effect=Exception("boom")
        ), patch("scraper.hardtraxx.time.sleep"):
            with pytest.raises(Exception, match="Error fetching tracks"):
                scraper.fetch_tracks()


class TestIntegration:
    def test_exported_from_scraper_package(self):
        # The provider must be available for use without being active.
        import scraper

        assert hasattr(scraper, "HardTraxx")

    def test_not_wired_into_main_sync_loop(self):
        # Hardtraxx is a dormant provider: main.py must not reference it.
        main_source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        assert not re.search(r"hardtraxx", main_source, flags=re.IGNORECASE)
