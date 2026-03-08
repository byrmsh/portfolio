import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { Redis } from 'ioredis';
import { pathToFileURL } from 'node:url';

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
const localDevOrigins = new Set([
  'http://localhost:4321',
  'http://127.0.0.1:4321',
  'http://localhost:3000',
  'http://127.0.0.1:3000',
]);
const configuredWebOrigins = new Set(
  [
    process.env.WEB_ORIGIN,
    process.env.PUBLIC_WEB_ORIGIN,
    process.env.CORS_ORIGIN,
    process.env.CORS_ORIGINS,
  ]
    .flatMap((value) => String(value ?? '').split(','))
    .map((value) => value.trim())
    .filter(Boolean),
);
const allowedCorsOrigins = new Set([...localDevOrigins, ...configuredWebOrigins]);

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
  start.setUTCDate(end.getUTCDate() - 6);

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

app.use(
  '/api/*',
  cors({
    origin: (origin) => {
      if (!origin) return undefined;
      return allowedCorsOrigins.has(origin) ? origin : undefined;
    },
  }),
);

app.get('/health', (c) => {
  return c.json({ data: { status: 'ok' }, meta: { ts: new Date().toISOString() } });
});

app.get('/api/status', async (c) => {
  const routeStartMs = Date.now();
  const freshnessMs = 24 * 60 * 60 * 1000;
  const checkedAt = new Date().toISOString();
  type ServiceStatus = 'healthy' | 'partial' | 'degraded' | 'unknown';

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

  const statusFromAge = (iso: string | null): ServiceStatus => {
    const ageMs = msAgo(iso);
    if (ageMs === null) return 'unknown';
    return ageMs <= freshnessMs ? 'healthy' : 'degraded';
  };

  const combineStatus = (statuses: ServiceStatus[]): ServiceStatus => {
    if (statuses.some((status) => status === 'degraded')) return 'degraded';
    if (statuses.some((status) => status === 'partial')) return 'partial';
    if (statuses.some((status) => status === 'unknown')) return 'unknown';
    return 'healthy';
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

  const readLyricistHeartbeat = async (): Promise<{
    lastRunAt: string | null;
    lastSuccessAt: string | null;
  }> => {
    try {
      const raw = await redis.get(redisKeys.stat('ytmusic', 'worker'));
      if (!raw) return { lastRunAt: null, lastSuccessAt: null };
      const parsed = JSON.parse(raw) as { lastRunAt?: unknown; lastSuccessAt?: unknown };
      return {
        lastRunAt: parseIsoOrNull(parsed.lastRunAt),
        lastSuccessAt: parseIsoOrNull(parsed.lastSuccessAt),
      };
    } catch {
      return { lastRunAt: null, lastSuccessAt: null };
    }
  };

  const probeRedis = async (): Promise<number | null> => {
    const start = Date.now();
    try {
      await redis.ping();
      return Math.max(1, Date.now() - start);
    } catch {
      return null;
    }
  };

  const [githubUpdatedAt, ankiUpdatedAt, dragonflyLatency, lyricistHeartbeat] = await Promise.all([
    readActivityUpdatedAt('github'),
    readActivityUpdatedAt('anki'),
    probeRedis(),
    readLyricistHeartbeat(),
  ]);

  const collectorRunsRaw = [githubUpdatedAt, ankiUpdatedAt].filter((value): value is string =>
    Boolean(value),
  ).length;
  const collectorMeta = `GitHub ${agoLabel(githubUpdatedAt)} • Anki ${agoLabel(ankiUpdatedAt)}`;

  const collectorStatus = combineStatus([
    statusFromAge(githubUpdatedAt),
    statusFromAge(ankiUpdatedAt),
  ]);
  const lyricistLastUpdatedAt = lyricistHeartbeat.lastSuccessAt ?? lyricistHeartbeat.lastRunAt;
  const lyricistStatus = statusFromAge(lyricistLastUpdatedAt);
  const dragonflyStatus: ServiceStatus = dragonflyLatency === null ? 'degraded' : 'healthy';
  const collectorLastUpdatedAt =
    [githubUpdatedAt, ankiUpdatedAt]
      .filter((value): value is string => Boolean(value))
      .map((value) => ({ value, ts: Date.parse(value) }))
      .filter((entry) => !Number.isNaN(entry.ts))
      .sort((a, b) => b.ts - a.ts)[0]?.value ?? null;
  const apiLatency = Math.max(1, Date.now() - routeStartMs);

  return c.json(
    {
      checkedAt,
      web: {
        status: 'unknown',
        latency: 0,
        message: 'Web health is measured by web runtime',
      },
      api: {
        status: 'healthy',
        latency: apiLatency,
        message: 'Hono process responding',
      },
      dragonfly: {
        status: dragonflyStatus,
        latency: dragonflyLatency ?? 0,
        message: dragonflyLatency === null ? 'Redis ping failed' : 'Redis ping successful',
      },
      collector: {
        status: collectorStatus,
        runs: collectorRunsRaw,
        message: collectorRunsRaw > 0 ? 'Collector tasks reported' : 'Collector has no reports yet',
        meta: collectorMeta,
      },
      lyricist: {
        status: lyricistStatus,
        runs: lyricistHeartbeat.lastRunAt ? 1 : 0,
        message: lyricistLastUpdatedAt
          ? 'Lyricist worker heartbeat reported'
          : 'Lyricist has no heartbeat yet',
        meta: `Last run ${agoLabel(lyricistHeartbeat.lastRunAt)} • Last success ${agoLabel(lyricistHeartbeat.lastSuccessAt)}`,
      },
      data: {
        checkedAt,
        uptimeSeconds: Math.floor(process.uptime()),
        collector: {
          lastUpdatedAt: collectorLastUpdatedAt,
        },
        lyricist: {
          lastRunAt: lyricistHeartbeat.lastRunAt,
          lastSuccessAt: lyricistHeartbeat.lastSuccessAt,
          lastUpdatedAt: lyricistLastUpdatedAt,
        },
      },
      meta: {
        ts: checkedAt,
        source: 'api',
      },
    },
    200,
  );
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

async function readSavedLyricsPage(page: number): Promise<{
  items: SavedLyricNote[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}> {
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

app.get('/api/ytmusic/analysis/pending/count', async (c) => {
  const pending = await redis.zcard(redisKeys.index.lyricsAnalysisPending);
  const envelope: ApiEnvelope<{ pending: number }> = {
    data: { pending },
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

export function startServer() {
  return serve({ fetch: app.fetch, port });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  startServer();
}

export default app;
