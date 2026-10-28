# Hardstyle Sonar

Scraping + synchronization program behind the Hardtsyle playlist, [Hardstyle Sonar](https://open.spotify.com/playlist/0J4ajfoQIajAnderVJZDgl?si=ebe5d9dda5af4ea9).

Every sync the scraped releases are matched and the playlist is created and
synced on both Spotify and Apple Music.

## Configuration

Credentials are read from the environment (or a `.env` file in the project
root).

### Spotify

```
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_PLAYLIST_ID=...
SPOTIFY_REFRESH_TOKEN=...
SPOTIFY_ACCESS_TOKEN=...
```

### Apple Music

The Apple Music playlist is managed through MusicKit. You need an Apple Music
API key (media key) and a Music User Token for the user library:

```
APPLE_MUSIC_KEY_ID=...
APPLE_MUSIC_TEAM_ID=...
APPLE_MUSIC_PRIVATE_KEY=...         # contents of the .p8 key
APPLE_MUSIC_PRIVATE_KEY_PATH=...    # or a path to the .p8 key (alternative)
APPLE_MUSIC_USER_TOKEN=...
APPLE_MUSIC_PLAYLIST_ID=...         # optional, playlist is created when empty
APPLE_MUSIC_PLAYLIST_NAME=Hardstyle Sonar
APPLE_MUSIC_STOREFRONT=nl
APPLE_MUSIC_RECREATE_ON_REMOVE=true # see below
```

When `APPLE_MUSIC_PLAYLIST_ID` is not set, the playlist is looked up by name
and created if it does not exist yet, so re-running the sync never creates
duplicate playlists.

The Apple Music API has no endpoint for removing individual tracks from a
library playlist. When tracks need to be removed, the playlist is therefore
recreated with the correct track list (mirroring the Spotify playlist). Set
`APPLE_MUSIC_RECREATE_ON_REMOVE=false` to keep the existing playlist and only
add new tracks instead.
