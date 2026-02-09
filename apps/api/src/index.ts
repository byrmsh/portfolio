import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { Redis } from 'ioredis';

import {
  activityMonitorDataSchema,
  activitySeriesSchema,
  redisKeys,
  type ActivitySource,
  type ActivitySeries,
  type ApiEnvelope,
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
  const parsed = activitySeriesSchema.parse(JSON.parse(raw));
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

const port = Number(process.env.PORT ?? 3000);
serve({ fetch: app.fetch, port });

export default app;
