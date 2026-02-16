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
  type JobDetail,
  type JobLead,
  type SavedLyricNote,
  type YtMusicAnalysis,
} from '@portfolio/schema/dashboard';

import { parseJobBoardJob, projectJobBoardJobToDetail } from './jobs/job-board.js';

const app = new Hono();

const redis = new Redis(process.env.REDIS_URL ?? 'redis://localhost:6379/0');

const JOB_CACHE_TTL_MS = 15 * 60 * 1000;
const jobCache = new Map<string, { expiresAt: number; value: JobDetail }>();

function cacheGetJob(id: string): JobDetail | null {
  const entry = jobCache.get(id);
  if (!entry) return null;
  if (Date.now() >= entry.expiresAt) {
    jobCache.delete(id);
    return null;
  }
  return entry.value;
}

function cachePutJob(detail: JobDetail): void {
  jobCache.set(detail.id, { value: detail, expiresAt: Date.now() + JOB_CACHE_TTL_MS });
}

function clampInt(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.trunc(n)));
}

type JobsCursor = { page: number; offset: number };

function decodeJobsCursor(raw: string | null): JobsCursor {
  if (!raw) return { page: 1, offset: 0 };
  const trimmed = raw.trim();
  if (/^\d+$/.test(trimmed)) return { page: clampInt(Number(trimmed), 1, 100000), offset: 0 };

  try {
    const json = Buffer.from(trimmed, 'base64url').toString('utf8');
    const parsed = JSON.parse(json) as { page?: unknown; offset?: unknown };
    const page =
      typeof parsed.page === 'number' ? clampInt(parsed.page, 1, 100000) : 1;
    const offset =
      typeof parsed.offset === 'number' ? clampInt(parsed.offset, 0, 500) : 0;
    return { page, offset };
  } catch {
    return { page: 1, offset: 0 };
  }
}

function encodeJobsCursor(cur: JobsCursor): string {
  return Buffer.from(JSON.stringify(cur), 'utf8').toString('base64url');
}

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

  const probeRedis = async (): Promise<number | null> => {
    const start = Date.now();
    try {
      await redis.ping();
      return Math.max(1, Date.now() - start);
    } catch {
      return null;
    }
  };

  const [githubUpdatedAt, ankiUpdatedAt, dragonflyLatency] = await Promise.all([
    readActivityUpdatedAt('github'),
    readActivityUpdatedAt('anki'),
    probeRedis(),
  ]);

  const collectorRunsRaw = [githubUpdatedAt, ankiUpdatedAt].filter((value): value is string =>
    Boolean(value),
  ).length;
  const collectorMeta = `GitHub ${agoLabel(githubUpdatedAt)} • Anki ${agoLabel(ankiUpdatedAt)}`;

  const collectorStatus = combineStatus([
    statusFromAge(githubUpdatedAt),
    statusFromAge(ankiUpdatedAt),
  ]);
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
      data: {
        checkedAt,
        uptimeSeconds: Math.floor(process.uptime()),
        collector: {
          lastUpdatedAt: collectorLastUpdatedAt,
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

app.get('/api/jobs', (c) => {
  return (async () => {
    const limitRaw = c.req.query('limit');
    const limit = clampInt(Number.parseInt(limitRaw ?? '20', 10) || 20, 1, 50);
    const beforeRaw = c.req.query('before');
    const cursor = decodeJobsCursor(beforeRaw ?? null);
    const capturedAtIso = new Date().toISOString();

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);

    let data: unknown[] = [];
    let hasNext = false;
    try {
      const res = await fetch(`https://www.arbeitnow.com/api/job-board-api?page=${cursor.page}`, {
        headers: { accept: 'application/json' },
        signal: controller.signal,
      });
      const json = (await res.json()) as {
        data?: unknown;
        links?: { next?: unknown } | null;
      };
      data = Array.isArray(json?.data) ? json.data : [];
      hasNext = Boolean(json?.links && (json.links as { next?: unknown }).next);
    } catch {
      data = [];
      hasNext = false;
    } finally {
      clearTimeout(timeout);
    }

    const parsed = data.map(parseJobBoardJob).filter((v): v is NonNullable<typeof v> => !!v);
    const slice = parsed.slice(cursor.offset, cursor.offset + limit);

    const items: JobLead[] = [];
    for (const job of slice) {
      const detail = projectJobBoardJobToDetail(job, capturedAtIso);
      if (!detail) continue;
      cachePutJob(detail);
      const lead: JobLead = {
        id: detail.id,
        source: detail.source,
        title: detail.title,
        summary: detail.summary,
        tags: detail.tags,
        publishedAt: detail.publishedAt,
        capturedAt: detail.capturedAt,
        href: detail.href,
        companyName: detail.companyName,
        location: detail.location,
        remote: detail.remote,
        jobTypes: detail.jobTypes,
      };
      items.push(lead);
    }

    const nextOffset = cursor.offset + slice.length;
    const nextCursor =
      slice.length === 0
        ? null
        : nextOffset < parsed.length
          ? encodeJobsCursor({ page: cursor.page, offset: nextOffset })
          : hasNext
            ? encodeJobsCursor({ page: cursor.page + 1, offset: 0 })
            : null;

    const envelope: ApiEnvelope<{ items: JobLead[]; nextCursor: string | null }> = {
      data: { items, nextCursor },
      meta: { ts: new Date().toISOString(), source: 'public' },
    };
    return c.json(envelope);
  })();
});

app.get('/api/jobs/:id', (c) => {
  return (async () => {
    const jobId = c.req.param('id');

    const cached = cacheGetJob(jobId);
    if (cached) {
      const envelope: ApiEnvelope<JobDetail> = {
        data: cached,
        meta: { ts: new Date().toISOString(), source: 'public', cache: 'hit' },
      };
      return c.json(envelope);
    }

    const capturedAtIso = new Date().toISOString();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);

    const cursorRaw = c.req.query('cursor');
    const cursorPage = cursorRaw ? decodeJobsCursor(cursorRaw ?? null).page : null;
    const scanPages = clampInt(
      Number.parseInt(c.req.query('page') ?? '', 10) || cursorPage || 1,
      1,
      100000,
    );
    const maxPages = 5;

    try {
      for (let p = scanPages; p < scanPages + maxPages; p += 1) {
        const res = await fetch(`https://www.arbeitnow.com/api/job-board-api?page=${p}`, {
          headers: { accept: 'application/json' },
          signal: controller.signal,
        });
        const json = (await res.json()) as { data?: unknown };
        const rows = Array.isArray(json?.data) ? json.data : [];
        const parsed = rows.map(parseJobBoardJob).filter((v): v is NonNullable<typeof v> => !!v);
        const found = parsed.find((j) => j.slug === jobId);
        if (!found) continue;

        const detail = projectJobBoardJobToDetail(found, capturedAtIso);
        if (!detail) return c.json({ error: 'invalid record' }, 500);
        cachePutJob(detail);
        const envelope: ApiEnvelope<JobDetail> = {
          data: detail,
          meta: { ts: new Date().toISOString(), source: 'public' },
        };
        return c.json(envelope);
      }
    } catch {
      // fall through
    } finally {
      clearTimeout(timeout);
    }

    return c.json({ error: 'not found' }, 404);
  })();
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
serve({ fetch: app.fetch, port });

export default app;
