import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { Redis } from 'ioredis';

import {
  activityMonitorDataSchema,
  activitySeriesSchema,
  jobDetailSchema,
  jobLeadSchema,
  jobRedisRecordSchema,
  redisKeys,
  savedLyricNoteSchema,
  ytmusicAnalysisSchema,
  type ActivitySource,
  type ActivitySeries,
  type ApiEnvelope,
  type JobDetail,
  type JobLead,
  type JobRedisRecord,
  type SavedLyricNote,
  type YtMusicAnalysis,
} from '@portfolio/schema/dashboard';
import { upworkJobResultSchema, type UpworkJobResult } from '@portfolio/schema/upwork';

const app = new Hono();

const redis = new Redis(process.env.REDIS_URL ?? 'redis://localhost:6379/0');

function clampInt(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.trunc(n)));
}

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function parseUnixSecondsToIso(value: unknown): string | null {
  const raw = typeof value === 'string' ? value.trim() : value;
  const n = typeof raw === 'number' ? raw : typeof raw === 'string' ? Number(raw) : NaN;
  if (!Number.isFinite(n) || n <= 0) return null;
  return new Date(n * 1000).toISOString();
}

function parseMaybeEpochToIso(value: unknown): string | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    const ms = value > 1e12 ? value : value * 1000;
    return new Date(ms).toISOString();
  }
  if (typeof value === 'string') {
    const s = value.trim();
    if (/^\d+$/.test(s)) {
      const n = Number(s);
      if (!Number.isFinite(n) || n <= 0) return null;
      const ms = s.length > 10 ? n : n * 1000;
      return new Date(ms).toISOString();
    }
    const ts = Date.parse(s);
    if (!Number.isNaN(ts)) return new Date(ts).toISOString();
  }
  return null;
}

function summarize(text: string, maxLen: number): string {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (clean.length <= maxLen) return clean;
  return `${clean.slice(0, Math.max(0, maxLen - 1)).trim()}…`;
}

function uniq<T>(values: T[]): T[] {
  const out: T[] = [];
  const seen = new Set<T>();
  for (const v of values) {
    if (seen.has(v)) continue;
    seen.add(v);
    out.push(v);
  }
  return out;
}

function upworkJobHref(job: UpworkJobResult): string | undefined {
  const ciphertext = asNonEmptyString(job?.jobTile?.job?.ciphertext);
  if (!ciphertext) return undefined;
  const clean = ciphertext.replace(/^~+/, '');
  return `https://www.upwork.com/jobs/~${encodeURIComponent(clean)}`;
}

function projectUpworkJobToLead(job: UpworkJobResult, capturedAtIso: string | null): JobLead | null {
  const publishedAt =
    parseMaybeEpochToIso(job?.jobTile?.job?.publishTime) ??
    parseMaybeEpochToIso(job?.jobTile?.job?.createTime) ??
    null;
  const capturedAt = capturedAtIso ?? publishedAt ?? new Date().toISOString();

  const tags = uniq(
    (Array.isArray(job.ontologySkills) ? job.ontologySkills : [])
      .map((s) => asNonEmptyString((s as { prettyName?: unknown }).prettyName))
      .filter((v): v is string => Boolean(v)),
  ).slice(0, 6);

  const lead = {
    id: String(job.id),
    source: 'upwork' as const,
    title: String(job.title ?? '').trim(),
    summary: summarize(String(job.description ?? ''), 180),
    tags: tags.length ? tags : ['Upwork'],
    publishedAt: publishedAt ?? new Date().toISOString(),
    capturedAt,
    href: upworkJobHref(job),
  };

  const parsed = jobLeadSchema.safeParse(lead);
  return parsed.success ? parsed.data : null;
}

function projectUpworkJobToRecord(job: UpworkJobResult, capturedAtIso: string | null): JobRedisRecord | null {
  const base = projectUpworkJobToLead(job, capturedAtIso);
  if (!base) return null;
  const record = {
    ...base,
    description: String(job.description ?? '').trim(),
  };
  const parsed = jobRedisRecordSchema.safeParse(record);
  return parsed.success ? parsed.data : null;
}

function projectUpworkJobToDetail(job: UpworkJobResult, capturedAtIso: string | null): JobDetail | null {
  const base = projectUpworkJobToRecord(job, capturedAtIso);
  if (!base) return null;

  const jobNode = job?.jobTile?.job;
  const detail = {
    ...base,
    jobType: jobNode?.jobType,
    hourlyBudgetMin: jobNode?.hourlyBudgetMin ?? null,
    hourlyBudgetMax: jobNode?.hourlyBudgetMax ?? null,
    weeklyRetainerBudget: jobNode?.weeklyRetainerBudget ?? null,
    fixedPriceAmount: jobNode?.fixedPriceAmount ?? null,
    contractorTier: asNonEmptyString(jobNode?.contractorTier) ?? undefined,
    enterpriseJob: typeof jobNode?.enterpriseJob === 'boolean' ? jobNode.enterpriseJob : undefined,
    premium: typeof jobNode?.premium === 'boolean' ? jobNode.premium : undefined,
    personsToHire: typeof jobNode?.personsToHire === 'number' ? jobNode.personsToHire : undefined,
    totalApplicants: typeof jobNode?.totalApplicants === 'number' ? jobNode.totalApplicants : null,
    client: job?.upworkHistoryData?.client
      ? {
          country: job.upworkHistoryData.client.country ?? null,
          paymentVerificationStatus: job.upworkHistoryData.client.paymentVerificationStatus ?? null,
          totalReviews: job.upworkHistoryData.client.totalReviews,
          totalFeedback: job.upworkHistoryData.client.totalFeedback,
          totalSpent: job.upworkHistoryData.client.totalSpent ?? null,
        }
      : undefined,
  };

  const parsed = jobDetailSchema.safeParse(detail);
  return parsed.success ? parsed.data : null;
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
  const jobsStreamKey = process.env.REDIS_STREAM_KEY ?? 'jobs';
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

  const probeRedis = async (): Promise<number | null> => {
    const start = Date.now();
    try {
      await redis.ping();
      return Math.max(1, Date.now() - start);
    } catch {
      return null;
    }
  };

  const [githubUpdatedAt, ankiUpdatedAt, upworkerLastFetchedAt, dragonflyLatency] = await Promise.all([
    readActivityUpdatedAt('github'),
    readActivityUpdatedAt('anki'),
    readUpworkerLastFetchedAt(),
    probeRedis(),
  ]);

  const collectorRunsRaw = [githubUpdatedAt, ankiUpdatedAt].filter((value): value is string => Boolean(value)).length;
  const upworkerRunsRaw = upworkerLastFetchedAt ? 1 : 0;
  const collectorMeta = `GitHub ${agoLabel(githubUpdatedAt)} • Anki ${agoLabel(ankiUpdatedAt)}`;

  const collectorStatus = combineStatus([statusFromAge(githubUpdatedAt), statusFromAge(ankiUpdatedAt)]);
  const upworkerFreshMs = msAgo(upworkerLastFetchedAt);
  const upworkerStatus: ServiceStatus =
    upworkerFreshMs === null ? 'unknown' : upworkerFreshMs <= freshnessMs ? 'healthy' : 'partial';
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
      upworker: {
        status: upworkerStatus,
        runs: upworkerRunsRaw,
        message: upworkerRunsRaw > 0 ? 'Jobs stream active' : 'Jobs stream missing',
        lastFetchedAt: upworkerLastFetchedAt,
      },
      data: {
        checkedAt,
        uptimeSeconds: Math.floor(process.uptime()),
        collector: {
          lastUpdatedAt: collectorLastUpdatedAt,
        },
        upworker: {
          lastFetchedAt: upworkerLastFetchedAt,
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
    const streamKey = process.env.REDIS_STREAM_KEY ?? 'jobs';
    const limitRaw = c.req.query('limit');
    const beforeRaw = c.req.query('before');
    const limit = clampInt(Number.parseInt(limitRaw ?? '20', 10) || 20, 1, 50);
    const before = typeof beforeRaw === 'string' && beforeRaw.trim().length > 0 ? beforeRaw.trim() : null;

    let rows: Array<[string, string[]]> = [];
    try {
      const count = before ? limit + 1 : limit;
      rows = await redis.xrevrange(streamKey, before ?? '+', '-', 'COUNT', count);
    } catch {
      rows = [];
    }

    if (before && rows.length && rows[0]?.[0] === before) rows.shift();
    if (rows.length > limit) rows = rows.slice(0, limit);

    const entries = rows
      .map(([id, kv]) => {
        let jobId = '';
        for (let i = 0; i < kv.length - 1; i += 2) {
          if (kv[i] === 'job_id') {
            jobId = String(kv[i + 1] ?? '').trim();
            break;
          }
        }
        if (!jobId) jobId = String(id).split('-')[0] ?? '';
        return { streamId: id, kv, jobId };
      })
      .filter((e) => e.jobId.length > 0);

    if (!entries.length) {
      const envelope: ApiEnvelope<{ items: JobLead[]; nextCursor: string | null }> = {
        data: { items: [], nextCursor: null },
        meta: { ts: new Date().toISOString(), source: 'redis' },
      };
      return c.json(envelope);
    }

    const pipeline = redis.pipeline();
    for (const e of entries) pipeline.get(redisKeys.job(e.jobId));
    const rawJobs = await pipeline.exec();

    const items: JobLead[] = [];
    for (let i = 0; i < entries.length; i += 1) {
      const streamKv = entries[i]?.kv ?? [];
      let fetchedAtIso: string | null = null;
      for (let j = 0; j < streamKv.length - 1; j += 2) {
        if (streamKv[j] === 'fetched_at') {
          fetchedAtIso = parseUnixSecondsToIso(streamKv[j + 1]);
          break;
        }
      }

      const entry = rawJobs?.[i];
      const raw = entry?.[1];
      if (typeof raw !== 'string') continue;

      try {
        const upwork = upworkJobResultSchema.parse(JSON.parse(raw) as unknown);
        const lead = projectUpworkJobToLead(upwork, fetchedAtIso);
        if (lead) items.push(lead);
      } catch {
        // Skip malformed historical records.
      }
    }

    const nextCursor = entries.length ? entries[entries.length - 1]!.streamId : null;
    const envelope: ApiEnvelope<{ items: JobLead[]; nextCursor: string | null }> = {
      data: { items, nextCursor },
      meta: { ts: new Date().toISOString(), source: 'redis' },
    };
    return c.json(envelope);
  })();
});

app.get('/api/jobs/:id', (c) => {
  return (async () => {
    const streamKey = process.env.REDIS_STREAM_KEY ?? 'jobs';
    const jobId = c.req.param('id');
    const raw = await redis.get(redisKeys.job(jobId));
    if (!raw) return c.json({ error: 'not found' }, 404);

    let fetchedAtIso: string | null = null;
    try {
      const rows = await redis.xrange(streamKey, `${jobId}-0`, `${jobId}-0`, 'COUNT', 1);
      const first = rows?.[0];
      if (first) {
        const [, kv] = first;
        for (let i = 0; i < kv.length - 1; i += 2) {
          if (kv[i] === 'fetched_at') {
            fetchedAtIso = parseUnixSecondsToIso(kv[i + 1]);
            break;
          }
        }
      }
    } catch {
      fetchedAtIso = null;
    }

    try {
      const upwork = upworkJobResultSchema.parse(JSON.parse(raw) as unknown);
      const detail = projectUpworkJobToDetail(upwork, fetchedAtIso);
      if (!detail) return c.json({ error: 'invalid record' }, 500);
      const envelope: ApiEnvelope<JobDetail> = {
        data: detail,
        meta: { ts: new Date().toISOString(), source: 'redis' },
      };
      return c.json(envelope);
    } catch {
      return c.json({ error: 'invalid record' }, 500);
    }
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
