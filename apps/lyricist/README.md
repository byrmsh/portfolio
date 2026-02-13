# Lyricist

Scheduled worker that syncs a YT Music playlist and generates public-safe lyric notes:

- background analysis (no lyric quoting)
- vocabulary explanations (no lyric quoting)

Outputs are written to Redis (DragonflyDB) for `apps/api` + `apps/web` to serve.
