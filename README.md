# Hardstyle Sonar

Scraping + synchronization program behind the Hardtsyle playlist, [Hardstyle Sonar](https://open.spotify.com/playlist/0J4ajfoQIajAnderVJZDgl?si=ebe5d9dda5af4ea9).

## YouTube livesets playlist

Besides the Spotify playlist sync, Hardstyle Sonar also collects the latest
livesets that have a YouTube video from
[hardtraxx.com](https://hardtraxx.com/livesets/?tab=event&playable=1) and adds
them to a YouTube playlist. Videos are kept in the playlist for at least 30
days before they are removed.

### Configuration

Add the following variables to your `.env`:

```
YOUTUBE_CLIENT_ID=        # Google OAuth client id
YOUTUBE_CLIENT_SECRET=    # Google OAuth client secret
YOUTUBE_REFRESH_TOKEN=    # OAuth refresh token with the YouTube scope
YOUTUBE_PLAYLIST_ID=      # Optional: id of an existing playlist to reuse
YOUTUBE_PLAYLIST_TITLE=   # Optional: title to look up / create (default: Hardstyle Sonar Livesets)
```

When `YOUTUBE_PLAYLIST_ID` is not set, the playlist is looked up by title and
created when it does not exist yet.

