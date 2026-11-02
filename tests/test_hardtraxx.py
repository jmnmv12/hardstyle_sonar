from datetime import datetime, timedelta, timezone

import pytest

import scraper.hardtraxx as hardtraxx_module
from scraper import HardTraxx
from scraper.models import Genre


class FakeResponse:
    def __init__(self, content: str):
        self.content = content.encode("utf-8")


LIST_PAGE_HTML = """
<html><body>
<dl class="row-item htx-topic-row htx-topic-row-side htx-topic-row-thumb topic_read">
  <dt class="htx-topic-main">
    <div class="list-inner min-w-0 flex-1">
      <div class="htx-topic-title is-spaceless">
        <a class="topictitle htx-topic-link"
           href="https://hardtraxx.com/livesets/set-a-t91379.html"
           title="Set A @ Festival 2026">Set A @ Festival 2026</a>
      </div>
      <div class="topic-poster htx-topic-poster">
        <span class="htx-genre-mark" title="Hardstyle">HS</span>
        <span class="shrink-0">Event set</span>
        <time class="num shrink-0" datetime="2026-11-02" title="Posted">2 Nov</time>
      </div>
    </div>
  </dt>
</dl>
<dl class="row-item htx-topic-row htx-topic-row-side htx-topic-row-thumb topic_read">
  <dt class="htx-topic-main">
    <div class="list-inner min-w-0 flex-1">
      <div class="htx-topic-title is-spaceless">
        <a class="topictitle htx-topic-link"
           href="https://hardtraxx.com/livesets/set-b-t91219.html"
           title="Set B @ Event 2026">Set B @ Event 2026</a>
      </div>
      <div class="topic-poster htx-topic-poster">
        <span class="htx-genre-mark" title="Hardcore">HC</span>
        <span class="shrink-0">Event set</span>
        <time class="num shrink-0" datetime="2026-10-30" title="Posted">30 Oct</time>
      </div>
    </div>
  </dt>
</dl>
</body></html>
"""

DETAIL_PAGE_WITH_YOUTUBE = """
<html><body>
  <a href="https://www.youtube.com/watch?v=yiNW06dBTAM" title="Open on YouTube">YouTube</a>
</body></html>
"""

DETAIL_PAGE_WITH_EMBED = """
<html><body>
  <iframe src="https://www.youtube.com/embed/A6X2B8F5QvI"></iframe>
</body></html>
"""

DETAIL_PAGE_WITHOUT_YOUTUBE = """
<html><body><p>No video here</p></body></html>
"""


def _fake_web_request(monkeypatch, responses):
    """responses: dict url -> content string"""

    def fake_web_request(url, headers=None):
        assert headers is not None, "hardtraxx requests must send crawler headers"
        return FakeResponse(responses[url])

    monkeypatch.setattr(hardtraxx_module, "web_request", fake_web_request)
    monkeypatch.setattr(hardtraxx_module.time, "sleep", lambda s: None)


def test_parse_liveset_rows():
    scraper = HardTraxx(from_date=datetime(2026, 10, 1))
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(LIST_PAGE_HTML, "html.parser")
    rows = scraper._parse_liveset_rows(soup)

    assert len(rows) == 2
    assert rows[0]["title"] == "Set A @ Festival 2026"
    assert rows[0]["url"] == "https://hardtraxx.com/livesets/set-a-t91379.html"
    assert rows[0]["date"] == datetime(2026, 11, 2)
    assert rows[0]["genre"] == Genre.Hardstyle
    assert rows[1]["genre"] == Genre.Hardcore


def test_before_from_date():
    scraper = HardTraxx(from_date=datetime(2026, 10, 30))

    assert scraper._before_from_date(datetime(2026, 10, 29)) is True
    assert scraper._before_from_date(datetime(2026, 10, 30)) is False
    assert scraper._before_from_date(datetime(2026, 11, 2)) is False


def test_extract_youtube_video_id_watch_url():
    from bs4 import BeautifulSoup

    scraper = HardTraxx(from_date=datetime(2026, 11, 1))
    soup = BeautifulSoup(DETAIL_PAGE_WITH_YOUTUBE, "html.parser")

    assert scraper._extract_youtube_video_id(soup) == "yiNW06dBTAM"


def test_extract_youtube_video_id_embed_fallback():
    from bs4 import BeautifulSoup

    scraper = HardTraxx(from_date=datetime(2026, 11, 1))
    soup = BeautifulSoup(DETAIL_PAGE_WITH_EMBED, "html.parser")

    assert scraper._extract_youtube_video_id(soup) == "A6X2B8F5QvI"


def test_extract_youtube_video_id_missing():
    from bs4 import BeautifulSoup

    scraper = HardTraxx(from_date=datetime(2026, 11, 1))
    soup = BeautifulSoup(DETAIL_PAGE_WITHOUT_YOUTUBE, "html.parser")

    assert scraper._extract_youtube_video_id(soup) is None


def test_fetch_tracks(monkeypatch):
    _fake_web_request(
        monkeypatch,
        {
            "https://hardtraxx.com/livesets/?tab=event&playable=1": LIST_PAGE_HTML,
            "https://hardtraxx.com/livesets/set-a-t91379.html": DETAIL_PAGE_WITH_YOUTUBE,
            "https://hardtraxx.com/livesets/set-b-t91219.html": DETAIL_PAGE_WITHOUT_YOUTUBE,
        },
    )

    scraper = HardTraxx(from_date=datetime(2026, 10, 1))
    tracks = scraper.fetch_tracks()

    # Set B is skipped because it has no youtube video
    assert len(tracks) == 1
    assert tracks[0].title == "Set A @ Festival 2026"
    assert tracks[0].youtube_video_id == "yiNW06dBTAM"
    assert tracks[0].genre == Genre.Hardstyle
    assert tracks[0].release_date == datetime(2026, 11, 2)


def test_fetch_tracks_skips_rows_before_from_date(monkeypatch):
    _fake_web_request(
        monkeypatch,
        {
            "https://hardtraxx.com/livesets/?tab=event&playable=1": LIST_PAGE_HTML,
            "https://hardtraxx.com/livesets/set-a-t91379.html": DETAIL_PAGE_WITH_YOUTUBE,
            "https://hardtraxx.com/livesets/set-b-t91219.html": DETAIL_PAGE_WITH_EMBED,
        },
    )

    # from_date after both rows -> nothing may be scraped
    scraper = HardTraxx(from_date=datetime(2026, 12, 1))
    assert scraper.fetch_tracks() == []

    # from_date between the two rows -> only the newer row is scraped
    scraper = HardTraxx(from_date=datetime(2026, 10, 31))
    tracks = scraper.fetch_tracks()
    assert len(tracks) == 1
    assert tracks[0].youtube_video_id == "yiNW06dBTAM"


SAME_TITLE_LIST_PAGE_HTML = """
<html><body>
<dl class="row-item htx-topic-row">
  <dt class="htx-topic-main">
    <a class="topictitle" href="https://hardtraxx.com/livesets/set-a-t1.html"
       title="Same Title Set">Same Title Set</a>
    <span class="htx-genre-mark" title="Hardstyle">HS</span>
    <time datetime="2026-11-02">2 Nov</time>
  </dt>
</dl>
<dl class="row-item htx-topic-row">
  <dt class="htx-topic-main">
    <a class="topictitle" href="https://hardtraxx.com/livesets/set-b-t2.html"
       title="Same Title Set">Same Title Set</a>
    <span class="htx-genre-mark" title="Hardstyle">HS</span>
    <time datetime="2026-11-02">2 Nov</time>
  </dt>
</dl>
</body></html>
"""


def test_before_from_date_handles_timezone_aware_dates():
    scraper = HardTraxx(from_date=datetime(2026, 10, 30))

    # A timezone-aware date compared against a naive from_date must not
    # raise a TypeError
    assert (
        scraper._before_from_date(datetime(2026, 10, 29, tzinfo=timezone.utc))
        is True
    )
    assert (
        scraper._before_from_date(datetime(2026, 11, 2, tzinfo=timezone.utc))
        is False
    )


def test_fetch_tracks_keeps_same_title_with_distinct_youtube_ids(monkeypatch):
    _fake_web_request(
        monkeypatch,
        {
            "https://hardtraxx.com/livesets/?tab=event&playable=1": SAME_TITLE_LIST_PAGE_HTML,
            "https://hardtraxx.com/livesets/set-a-t1.html": DETAIL_PAGE_WITH_YOUTUBE,
            "https://hardtraxx.com/livesets/set-b-t2.html": DETAIL_PAGE_WITH_EMBED,
        },
    )

    scraper = HardTraxx(from_date=datetime(2026, 10, 1))
    tracks = scraper.fetch_tracks()

    # Two livesets with the same title but different youtube videos
    # must both be kept
    assert len(tracks) == 2
    assert {t.youtube_video_id for t in tracks} == {"yiNW06dBTAM", "A6X2B8F5QvI"}
