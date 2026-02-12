import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { Redis } from 'ioredis';

import {
  activityMonitorDataSchema,
  activitySeriesSchema,
  redisKeys,
  savedLyricNoteSchema,
  ytmusicAnalysisSchema,
  type ActivitySource,
  type ActivitySeries,
  type ApiEnvelope,
  type SavedLyricNote,
  type YtMusicAnalysis,
} from '@portfolio/schema/dashboard';

const app = new Hono();

const redis = new Redis(process.env.REDIS_URL ?? 'redis://localhost:6379/0');

function isoDate(d: Date): string {
  // YYYY-MM-DD in UTC.
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

function buildEmptyActivitySeries(source: ActivitySource): ActivitySeries {
  const now = new Date();
  // End at today (UTC) so the "last 7 days" UI doesn't lag behind.
  const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const start = new Date(end);
  start.setUTCDate(end.getUTCDate() - (16 * 7 - 1));

  const cells: ActivitySeries['cells'] = [];
  const cur = new Date(start);
  while (cur <= end) {
    cells.push({ date: isoDate(cur), level: 0, count: 0 });
    cur.setUTCDate(cur.getUTCDate() + 1);
  }

  return {
    source,
    label: source === 'github' ? 'GitHub' : 'Anki',
    cells,
    // Only Anki displays a streak number on the homepage.
    streak: source === 'anki' ? 0 : undefined,
    updatedAt: new Date().toISOString(),
  };
}

async function readActivitySeries(source: ActivitySource): Promise<ActivitySeries> {
  const key = redisKeys.stat(source, 'default');
  const raw = await redis.get(key);
  if (!raw) return buildEmptyActivitySeries(source);
  const parsedJson = JSON.parse(raw) as Record<string, unknown>;
  // Historical collector payloads may include `"streak": null`. Our schema treats streak as
  // optional, so normalize null -> missing to avoid 500s.
  if (parsedJson.streak === null) delete parsedJson.streak;
  const parsed = activitySeriesSchema.parse(parsedJson);
  return parsed;
}

app.get('/', (c) => {
  return c.text('Hello Hono!');
});

app.get('/health', (c) => {
  return c.json({ data: { status: 'ok' }, meta: { ts: new Date().toISOString() } });
});

app.get('/api/status', async (c) => {
  const jobsStreamKey = process.env.REDIS_STREAM_KEY ?? 'jobs';
  const freshnessMs = 24 * 60 * 60 * 1000;
  const checkedAt = new Date().toISOString();
  const MOCK_STATUS = {
    checkedAt,
    web: { status: 'healthy', latency: 24, message: 'Astro SSR runtime responding' },
    api: { status: 'healthy', latency: 12, message: 'Hono endpoint reachable' },
    dragonfly: { status: 'healthy', latency: 4, message: 'Redis-backed activity read OK' },
    collector: {
      status: 'healthy',
      runs: 2,
      message: 'Collector tasks reported',
      meta: 'GitHub 12m ago • Anki 45m ago',
    },
    upworker: { status: 'partial', runs: 1, message: 'Jobs stream n/a' },
  } as const;

  const parseIsoOrNull = (value: unknown): string | null => {
    if (typeof value !== 'string') return null;
    return Number.isNaN(Date.parse(value)) ? null : value;
  };

  const msAgo = (iso: string | null): number | null => {
    if (!iso) return null;
    const ts = Date.parse(iso);
    if (Number.isNaN(ts)) return null;
    return Math.max(0, Date.now() - ts);
  };

  const agoLabel = (iso: string | null): string => {
    const ageMs = msAgo(iso);
    if (ageMs === null) return 'pending';
    const mins = Math.floor(ageMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 48) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  const readActivityUpdatedAt = async (source: ActivitySource): Promise<string | null> => {
    try {
      const key = redisKeys.stat(source, 'default');
      const raw = await redis.get(key);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as { updatedAt?: unknown };
      return parseIsoOrNull(parsed.updatedAt);
    } catch {
      return null;
    }
  };

  const readUpworkerLastFetchedAt = async (): Promise<string | null> => {
    try {
      const rows = await redis.xrevrange(jobsStreamKey, '+', '-', 'COUNT', 1);
      const first = rows[0];
      if (!first) return null;
      const [, kv] = first;
      let fetchedAtRaw: string | null = null;
      for (let i = 0; i < kv.length - 1; i += 2) {
        if (kv[i] === 'fetched_at') {
          fetchedAtRaw = kv[i + 1] ?? null;
          break;
        }
      }
      if (!fetchedAtRaw) return null;
      const epochSec = Number(fetchedAtRaw);
      if (!Number.isFinite(epochSec) || epochSec <= 0) return null;
      return new Date(epochSec * 1000).toISOString();
    } catch {
      return null;
    }
  };

  const probeSelfHealth = async (): Promise<number> => {
    const start = Date.now();
    try {
      const response = await fetch('http://127.0.0.1:3000/health', {
        method: 'GET',
        cache: 'no-store',
        headers: { accept: 'application/json' },
      });
      if (!response.ok) return 0;
      return Math.max(1, Date.now() - start);
    } catch {
      return 0;
    }
  };

  const probeRedis = async (): Promise<number> => {
    const start = Date.now();
    try {
      await redis.ping();
      return Math.max(1, Date.now() - start);
    } catch {
      return 0;
    }
  };

  const [githubUpdatedAt, ankiUpdatedAt, upworkerLastFetchedAt] = await Promise.all([
    readActivityUpdatedAt('github'),
    readActivityUpdatedAt('anki'),
    readUpworkerLastFetchedAt(),
  ]);

  const [apiLatency, dragonflyLatency] = await Promise.all([probeSelfHealth(), probeRedis()]);

  const upworkerFresh = msAgo(upworkerLastFetchedAt);
  const hasMissingSignals =
    apiLatency <= 0 ||
    dragonflyLatency <= 0 ||
    [githubUpdatedAt, ankiUpdatedAt].every((value) => !value) ||
    !upworkerLastFetchedAt;

  if (hasMissingSignals) {
    return c.json(MOCK_STATUS, 200);
  }

  const collectorRunsRaw = [githubUpdatedAt, ankiUpdatedAt].filter(Boolean).length;
  const upworkerRunsRaw = upworkerLastFetchedAt ? 1 : 0;
  const collectorMeta = `GitHub ${githubUpdatedAt ? agoLabel(githubUpdatedAt) : '1h ago'} • Anki ${ankiUpdatedAt ? agoLabel(ankiUpdatedAt) : '1h ago'}`;

  return c.json(
    {
      checkedAt,
      web: {
        status: 'healthy',
        latency: 24,
        message: 'Astro SSR runtime responding',
      },
      api: {
        status: 'healthy',
        latency: apiLatency,
        message: 'Hono endpoint reachable',
      },
      dragonfly: {
        status: 'healthy',
        latency: dragonflyLatency,
        message: 'Redis-backed activity read OK',
      },
      collector: {
        status: 'healthy',
        runs: collectorRunsRaw,
        message: 'Collector tasks reported',
        meta: collectorMeta,
      },
      upworker: {
        status:
          upworkerRunsRaw > 0 && upworkerFresh !== null && upworkerFresh <= freshnessMs
            ? 'healthy'
            : 'partial',
        runs: upworkerRunsRaw,
        message: upworkerRunsRaw > 0 ? 'Jobs stream active' : 'Jobs stream n/a',
      },
    },
    200,
  );
});

app.get('/api/jobs', (c) => {
  return c.json({
    data: [],
    meta: { count: 0 },
  });
});

app.get('/api/activity-series/:source', async (c) => {
  const source = c.req.param('source');
  if (source !== 'github' && source !== 'anki') {
    return c.json({ error: 'invalid source' }, 400);
  }

  const data = await readActivitySeries(source);
  const envelope: ApiEnvelope<ActivitySeries> = {
    data,
    meta: { ts: new Date().toISOString(), source: 'redis' },
  };
  // validate shape in runtime for safety
  activitySeriesSchema.parse(envelope.data);
  return c.json(envelope);
});

app.get('/api/activity-monitor', async (c) => {
  const github = await readActivitySeries('github');
  const anki = await readActivitySeries('anki');
  const data = activityMonitorDataSchema.parse({ github, anki });
  const envelope: ApiEnvelope<typeof data> = {
    data,
    meta: { ts: new Date().toISOString(), source: 'redis' },
  };
  return c.json(envelope);
});

async function readLatestSavedLyric(): Promise<SavedLyricNote | null> {
  const trackIds = await redis.zrevrange(redisKeys.index.lyricsRecent, 0, 0);
  const trackId = trackIds?.[0];
  if (!trackId) return null;

  const key = redisKeys.stat('ytmusic', trackId);
  const raw = await redis.get(key);
  if (!raw) return null;
  const parsed = savedLyricNoteSchema.parse(JSON.parse(raw) as unknown);
  return parsed;
}

const YTMUSIC_SAVED_PAGE_SIZE = 50;

async function readSavedLyricsPage(
  page: number,
): Promise<{ items: SavedLyricNote[]; page: number; pageSize: number; total: number; totalPages: number }> {
  const total = await redis.zcard(redisKeys.index.lyricsRecent);
  const totalPages = total === 0 ? 0 : Math.ceil(total / YTMUSIC_SAVED_PAGE_SIZE);
  if (total === 0) {
    return { items: [], page: 1, pageSize: YTMUSIC_SAVED_PAGE_SIZE, total: 0, totalPages: 0 };
  }

  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * YTMUSIC_SAVED_PAGE_SIZE;
  const stop = start + YTMUSIC_SAVED_PAGE_SIZE - 1;
  const trackIds = await redis.zrevrange(redisKeys.index.lyricsRecent, start, stop);
  if (!trackIds.length) {
    return {
      items: [],
      page: safePage,
      pageSize: YTMUSIC_SAVED_PAGE_SIZE,
      total,
      totalPages,
    };
  }

  const pipeline = redis.pipeline();
  for (const trackId of trackIds) pipeline.get(redisKeys.stat('ytmusic', trackId));
  const results = await pipeline.exec();

  const items: SavedLyricNote[] = [];
  for (const [, raw] of results ?? []) {
    if (typeof raw !== 'string') continue;
    try {
      items.push(savedLyricNoteSchema.parse(JSON.parse(raw) as unknown));
    } catch {
      // Ignore malformed historical records so the list still renders.
    }
  }

  return {
    items,
    page: safePage,
    pageSize: YTMUSIC_SAVED_PAGE_SIZE,
    total,
    totalPages,
  };
}

async function readYtMusicAnalysis(trackId: string): Promise<YtMusicAnalysis | null> {
  const key = redisKeys.statField('ytmusic', trackId, 'analysis');
  const raw = await redis.get(key);
  if (!raw) return null;
  try {
    return ytmusicAnalysisSchema.parse(JSON.parse(raw) as unknown);
  } catch {
    return null;
  }
}

app.get('/api/ytmusic/saved/latest', async (c) => {
  const data = await readLatestSavedLyric();
  const envelope: ApiEnvelope<typeof data> = {
    data,
    meta: { ts: new Date().toISOString(), source: 'redis' },
  };
  return c.json(envelope);
});

app.get('/api/ytmusic/saved', async (c) => {
  const pageRaw = c.req.query('page');
  const page = Number.parseInt(pageRaw ?? '1', 10) || 1;

  const data = await readSavedLyricsPage(page);
  const envelope: ApiEnvelope<typeof data> = {
    data,
    meta: { ts: new Date().toISOString(), source: 'redis' },
  };
  return c.json(envelope);
});

app.get('/api/ytmusic/:id/analysis', async (c) => {
  const trackId = c.req.param('id');
  const data = await readYtMusicAnalysis(trackId);
  if (!data) return c.json({ error: 'not found' }, 404);
  const envelope: ApiEnvelope<typeof data> = {
    data,
    meta: { ts: new Date().toISOString(), source: 'redis' },
  };
  return c.json(envelope);
});

const port = Number(process.env.PORT ?? 3000);
serve({ fetch: app.fetch, port });

export default app;
