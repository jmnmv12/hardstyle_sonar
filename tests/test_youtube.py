from datetime import datetime, timedelta, timezone

from playlist import YouTube
from playlist.youtube import YouTubeItem


def _make_client():
    # No credentials -> no authentication call is made in the constructor
    return YouTube(playlist_id="PL_test")


def _playlist_item(video_id, added_at, playlist_item_id=None):
    return YouTubeItem(
        id=video_id,
        release_date=added_at,
        playlist_item_id=playlist_item_id or ("PI_" + video_id),
    )


def test_sync_adds_new_videos_and_keeps_recent_ones():
    youtube = _make_client()
    now = datetime(2026, 11, 2, 12, 0, 0)

    added = []
    removed = []
    youtube.add_playlist_items = lambda tracks: added.extend(tracks)
    youtube.remove_playlist_items = lambda tracks: removed.extend(tracks)

    playlist_data = [
        # In the playlist for 10 days and no longer in the scrape,
        # must be kept because of the 30 day retention
        _playlist_item("recentold", now - timedelta(days=10)),
        # In the playlist for 40 days and no longer in the scrape,
        # must be removed
        _playlist_item("veryold", now - timedelta(days=40)),
        # Still in the scrape, must never be removed
        _playlist_item("instill", now - timedelta(days=40)),
    ]
    scrape = [
        _playlist_item("instill", None),
        _playlist_item("brandnew", None),
    ]

    youtube.sync_playlist(playlist_data, scrape, retention_days=30, now=now)

    assert [item.id for item in added] == ["brandnew"]
    assert [item.id for item in removed] == ["veryold"]


def test_sync_keeps_items_with_unknown_age():
    youtube = _make_client()
    now = datetime(2026, 11, 2, 12, 0, 0)

    added = []
    removed = []
    youtube.add_playlist_items = lambda tracks: added.extend(tracks)
    youtube.remove_playlist_items = lambda tracks: removed.extend(tracks)

    playlist_data = [
        # No added date known -> may never be removed
        YouTubeItem(id="unknownage", release_date=None, playlist_item_id="PI_u"),
        # A plain Item-like object without added_at/release_date
        type("PlainItem", (), {"id": "plain", "release_date": None})(),
    ]

    youtube.sync_playlist(playlist_data, [], retention_days=30, now=now)

    assert added == []
    assert removed == []


def test_sync_handles_timezone_aware_dates():
    youtube = _make_client()
    now = datetime(2026, 11, 2, 12, 0, 0)

    added = []
    removed = []
    youtube.add_playlist_items = lambda tracks: added.extend(tracks)
    youtube.remove_playlist_items = lambda tracks: removed.extend(tracks)

    playlist_data = [
        # YouTube publishedAt values are timezone aware (e.g. Zulu time)
        _playlist_item(
            "awareold",
            (now - timedelta(days=45)).replace(tzinfo=timezone.utc),
        ),
    ]

    youtube.sync_playlist(playlist_data, [], retention_days=30, now=now)

    assert [item.id for item in removed] == ["awareold"]


def test_sync_noops_when_everything_matches():
    youtube = _make_client()
    now = datetime(2026, 11, 2, 12, 0, 0)

    added = []
    removed = []
    youtube.add_playlist_items = lambda tracks: added.extend(tracks)
    youtube.remove_playlist_items = lambda tracks: removed.extend(tracks)

    playlist_data = [_playlist_item("same", now - timedelta(days=90))]
    scrape = [type("PlainItem", (), {"id": "same"})()]

    youtube.sync_playlist(playlist_data, scrape, retention_days=30, now=now)

    assert added == []
    assert removed == []


def test_default_retention_is_30_days():
    import inspect

    signature = inspect.signature(YouTube.sync_playlist)
    assert signature.parameters["retention_days"].default == 30
