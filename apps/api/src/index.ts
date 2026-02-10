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

app.get('/api/status', (c) => {
  return c.json({
    data: {
      api: 'ok',
      uptimeSeconds: Math.floor(process.uptime()),
      timestamp: new Date().toISOString(),
    },
    meta: { source: 'placeholder' },
  });
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
