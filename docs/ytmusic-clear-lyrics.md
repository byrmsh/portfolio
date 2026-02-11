# YT Music: Clear Lyrics + Saved Lyric Notes

**Status:** Implemented baseline, iterating (updated 2026-02-11)
**Components:**
- Worker: `apps/lyricist` (Python + uv, CronJob)
- API: `apps/api` (Hono + ioredis)
- Web: `apps/web` (Astro + Svelte islands)

This doc replaces the earlier Gemini draft with a spec that matches repo conventions:
- Redis key helpers live in `packages/schema/src/dashboard.ts` (`redisKeys.*`) and `packages/schema-py/src/portfolio_schema/dashboard.py` (`RedisKeys.*`).
- User-facing "personal stats/content" records use `stat:{source}:{id}` (per `AGENTS.md` and `docs/frontend-data-model.md`).
- The homepage already has a `SavedLyricsCard` placeholder in `apps/web/src/components/SavedLyricsCard.astro` that should become data-driven.

## 1) What We Are Building

### MVP (ship first)

1. A worker syncs a configured YT Music playlist on a schedule.
2. It selects a track to "save" (latest new track, or a deterministic rule).
3. It generates a "lyric note" artifact:
   - The public site should not publish full lyrics.
   - The note is a short, original writeup (context + vocabulary + pointers/links).
4. It writes a `SavedLyricNote` record into Redis so the API/web can render the "Saved Lyrics" card.

### Phase 2 (optional)

Add deeper analysis pages (Genius-like) with a strict copyright-safe policy:
- No full lyric bodies stored/served publicly.
- If quoting is required, limit to short excerpts and store only what is necessary.

## 2) Copyright / Safety Boundary (Non-Negotiable)

The portfolio is public. We will treat song lyrics as copyrighted content.

Rules:
- Do not store full lyric text in Redis.
- Do not render full lyrics in `apps/web`.
- Generated notes must be original commentary plus links (YT Music / YouTube / Genius) rather than reproductions.

We are choosing the “analysis + links only” route (no lyrics ingestion), so there is no owner-only lyric display and no auth requirement for this feature.

## 3) Data Model (Redis)

We will reuse the existing shared schema type:
- `SavedLyricNote` in `packages/schema/src/dashboard.ts` and `packages/schema-py/src/portfolio_schema/dashboard.py`.

### Keys

Per `docs/frontend-data-model.md`, saved lyrics are:
- Primary record: `stat:ytmusic:{trackId}` (value = JSON `SavedLyricNote`)
- Index (optional but recommended): `index:ytmusic:saved` (sorted set; score = unix seconds; member = `{trackId}`)

We will also store a tiny cursor so the CronJob is idempotent:
- `stat:ytmusic:cursor` (string JSON; see below)

### Public Analysis Record

We will store a separate record for the public “Genius-like” output, without lyrics:
- `stat:ytmusic:{trackId}:analysis`: JSON “public analysis” (general meaning + vocabulary + links)

Proposed shape (stored as JSON; we will add validators in `packages/schema` / `packages/schema-py` when implementing).

Design goals:
- No lyric quotes.
- “Background notes” are original prose (what the song is about, references, tone, themes).
- “Vocabulary” is phrase/word-level explanation without quoting a lyric line; focus on literal meaning, idiomatic meaning, usage notes, and learner pitfalls.

```json
{
  "id": "dQw4w9WgXcQ",
  "source": "ytmusic",
  "title": "Atemlos durch die Nacht",
  "artist": "Helene Fischer",
  "album": "Farbenspiel",
  "albumArtUrl": "https://...",
  "trackUrl": "https://music.youtube.com/watch?v=...",
  "lyricsUrl": "https://genius.com/...",
  "background": {
    "tldr": "One-paragraph plain-English interpretation (no lyric quotes).",
    "notes": [
      {
        "title": "Theme",
        "body": "Original analysis of themes, tone, and subtext."
      },
      {
        "title": "Cultural context",
        "body": "Any relevant context a learner would miss."
      }
    ]
  },
  "vocabulary": [
    {
      "term": "jemanden still machen",
      "literal": "to make someone still (unmoving)",
      "meaning": "to kill someone (idiomatic / dark euphemism)",
      "cefr": "B2",
      "usage": [
        "Register: colloquial / slang (depends on region).",
        "Pitfall: do not use casually; can sound threatening."
      ]
    }
  ],
  "updatedAt": "2026-02-10T00:00:00.000Z"
}
```

### Cursor Payload

Stored at `stat:ytmusic:cursor`:

```json
{
  "playlistId": "PLxxxxxxxx",
  "lastSeenTrackId": "dQw4w9WgXcQ",
  "updatedAt": "2026-02-10T00:00:00.000Z"
}
```

## 4) Worker: `apps/lyricist` (CronJob)

### Why a New App (not `apps/collector`)

Same rationale as `apps/ankiworker`:
- heavier deps (`ytmusicapi`, optional `lyricsgenius`, optional `openai`)
- slower runtime (network + optional LLM)
- isolate failures from other collectors

### Schedule + Concurrency

- Run daily (or a few times/day) via K8s CronJob.
- `concurrencyPolicy: Forbid` (avoid overlapping playlist syncs).

### Inputs (Env Vars)

Non-secret:
- `REDIS_URL`
- `REDIS_EVENTS_STREAM` (default `events`, consistent with `packages/common-py`)
- `YTMUSIC_PLAYLIST_ID` (or URL; pick one and stick to it)
- `WEB_ORIGIN` (used to build absolute `noteUrl`, because TS schema currently requires a URL)

Secrets (K8s secret, never committed to YAML):
- `YTMUSIC_AUTH_JSON` (if needed by `ytmusicapi` auth mode)
- `GENIUS_ACCESS_TOKEN` (optional; lyrics lookup is not required for MVP)
- `LYRICIST_LLM_PROVIDER` (`auto|gemini|openai|none`; `auto` prefers Gemini if configured)
- `GEMINI_API_KEY` (optional; enables LLM analysis via Gemini)
- `GEMINI_MODEL` (optional; defaults to `gemini-1.5-flash`)
- `GEMINI_USE_SEARCH` (optional; enables Gemini Google Search grounding if the model supports it)
- `OPENAI_API_KEY` (optional; enables LLM analysis via OpenAI fallback)

### Outputs

1. Write `SavedLyricNote` JSON to `stat:ytmusic:{trackId}`.
2. Add `{trackId}` to `index:ytmusic:saved` with score = unix seconds (`savedAt`).
3. Update cursor at `stat:ytmusic:cursor`.
4. Emit an event to the Redis stream:
   - `type`: `ytmusic_saved_updated`
   - `payload`: `{ "trackId": "...", "key": "stat:ytmusic:{trackId}" }`
5. Write analysis to `stat:ytmusic:{trackId}:analysis`.

## 5) API

MVP endpoint(s) to power the homepage:

Option A (align with `docs/frontend-data-model.md`):
- Add `GET /api/dashboard` and include `savedLyric` populated from Redis (latest item from `index:ytmusic:saved`).

Option B (minimal surface area first):
- Add `GET /api/ytmusic/saved/latest` -> `ApiEnvelope<SavedLyricNote | null>`

Either way:
- validate responses with `@portfolio/schema` at the API boundary
- use `redisKeys.stat('ytmusic', trackId)` and `redisKeys.index.lyricsRecent` (`index:ytmusic:saved`)

## 6) Web

MVP:
- Make `apps/web/src/components/SavedLyricsCard.astro` fetch the latest saved lyric note from the API and render:
  - title
  - artist
  - link to `noteUrl`
  - album art if present

No `/music` route needed for MVP.
If we later add a dedicated route (e.g. `/lyrics/:trackId`), it should render only the analysis record plus outbound links to the lyric source.

## 7) Kubernetes / Helm

Primary deployment path:
- Helm chart: `deploy/helm/portfolio` (`collectorCronJobs.jobs` includes `lyricist-cronjob`)

Fallback/raw manifest:
- `deploy/k8s/06-lyricist-cronjob.yaml`

Constraints (from `AGENTS.md`):
- namespace: `portfolio`
- labels: `app: portfolio`, `component: collector` (closest fit for a scheduled worker)
- set requests/limits (start 128Mi)

Secrets: do not write them in YAML. Create them manually, e.g.:

```bash
kubectl create secret generic lyricist-secrets \
  --namespace portfolio \
  --from-literal=YTMUSIC_PLAYLIST_ID='YOUR_PLAYLIST_ID' \
  --from-literal=WEB_ORIGIN='https://YOUR_DOMAIN' \
  --from-literal=GENIUS_ACCESS_TOKEN='YOUR_TOKEN' \
  --from-literal=LYRICIST_LLM_PROVIDER='gemini' \
  --from-literal=GEMINI_API_KEY='YOUR_KEY' \
  --from-literal=GEMINI_MODEL='gemini-1.5-flash' \
  --from-literal=GEMINI_USE_SEARCH='true' \
  --from-literal=OPENAI_API_KEY='YOUR_KEY'
```

Note: `YTMUSIC_AUTH_JSON` is usually multiline; prefer `--from-file` when we wire it up.

## 8) Implementation Checklist

1. Worker skeleton: `apps/lyricist` (uv project, Redis client, structured logging)
2. Redis contract wiring:
   - write `SavedLyricNote` to `stat:ytmusic:{trackId}`
   - maintain `index:ytmusic:saved`
   - store cursor at `stat:ytmusic:cursor`
3. API: choose Option A or B and implement it in `apps/api`
4. Web: make `SavedLyricsCard` dynamic
5. K8s/Helm: keep `lyricist-cronjob` wired in Helm values/templates and maintain raw manifest fallback
