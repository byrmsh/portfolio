import type { APIRoute } from 'astro';

type ServiceStatus = 'healthy' | 'degraded' | 'unknown';
type ServiceId = 'web' | 'api' | 'collector' | 'upworker' | 'db';

type ServiceCheck = {
  id: string;
  label: string;
  status: ServiceStatus;
  updatedAt: string | null;
};

type ServiceProbe = {
  id: ServiceId;
  status: ServiceStatus;
  detail: string;
  latencyMs: number | null;
  checks?: ServiceCheck[];
};

type ProbeResult = {
  ok: boolean;
  latencyMs: number | null;
};

type ApiStatusPayload = {
  data?: {
    uptimeSeconds?: number;
    collector?: {
      lastUpdatedAt?: string | null;
    };
    upworker?: {
      lastFetchedAt?: string | null;
    };
  };
};

type ActivityMonitorPayload = {
  data?: {
    github?: {
      updatedAt?: string;
    };
    anki?: {
      updatedAt?: string;
    };
  };
};

function clampNonNegativeInt(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const intValue = Math.floor(value);
  return intValue >= 0 ? intValue : null;
}

function parseIsoDate(value: unknown): Date | null {
  if (typeof value !== 'string') return null;
  const ts = Date.parse(value);
  return Number.isNaN(ts) ? null : new Date(ts);
}

function statusFromFreshness(timestamp: Date | null, freshnessMs: number): ServiceStatus {
  if (!timestamp) return 'unknown';
  const ageMs = Date.now() - timestamp.getTime();
  return ageMs <= freshnessMs ? 'healthy' : 'degraded';
}

function combineStatuses(statuses: ServiceStatus[]): ServiceStatus {
  if (statuses.some((status) => status === 'degraded')) return 'degraded';
  if (statuses.some((status) => status === 'unknown')) return 'unknown';
  return 'healthy';
}

async function probe(url: string, timeoutMs: number): Promise<ProbeResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const start = Date.now();
  try {
    const response = await fetch(url, {
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal,
      headers: { accept: 'application/json' },
    });
    return {
      ok: response.ok,
      latencyMs: Date.now() - start,
    };
  } catch {
    return { ok: false, latencyMs: null };
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchActivityMonitor(url: string): Promise<{
  ok: boolean;
  latencyMs: number | null;
  githubUpdatedAt: Date | null;
  ankiUpdatedAt: Date | null;
}> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1500);
  const start = Date.now();
  try {
    const response = await fetch(url, {
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal,
      headers: { accept: 'application/json' },
    });
    const latencyMs = Date.now() - start;
    if (!response.ok) {
      return { ok: false, latencyMs, githubUpdatedAt: null, ankiUpdatedAt: null };
    }
    const payload = (await response.json()) as ActivityMonitorPayload;
    return {
      ok: true,
      latencyMs,
      githubUpdatedAt: parseIsoDate(payload?.data?.github?.updatedAt),
      ankiUpdatedAt: parseIsoDate(payload?.data?.anki?.updatedAt),
    };
  } catch {
    return { ok: false, latencyMs: null, githubUpdatedAt: null, ankiUpdatedAt: null };
  } finally {
    clearTimeout(timeout);
  }
}

async function readApiStatus(url: string): Promise<ApiStatusPayload | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1500);
  try {
    const response = await fetch(url, {
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal,
      headers: { accept: 'application/json' },
    });
    if (!response.ok) return null;
    return (await response.json()) as ApiStatusPayload;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function overallStatus(services: ServiceProbe[]): ServiceStatus {
  if (services.some((service) => service.status === 'degraded')) return 'degraded';
  if (services.some((service) => service.status === 'unknown')) return 'unknown';
  return 'healthy';
}

export const GET: APIRoute = async ({ request }) => {
  const apiOrigin =
    process.env.API_ORIGIN ??
    import.meta.env.API_ORIGIN ??
    import.meta.env.PUBLIC_API_ORIGIN ??
    'http://localhost:3000';

  const webHealthUrl = new URL('/health', request.url).toString();
  const apiHealthUrl = `${apiOrigin.replace(/\/$/, '')}/health`;
  const apiActivityUrl = `${apiOrigin.replace(/\/$/, '')}/api/activity-monitor`;
  const apiStatusUrl = `${apiOrigin.replace(/\/$/, '')}/api/status`;

  const [webProbe, apiProbe, activityMonitor, apiStatus] = await Promise.all([
    probe(webHealthUrl, 1200),
    probe(apiHealthUrl, 1200),
    fetchActivityMonitor(apiActivityUrl),
    readApiStatus(apiStatusUrl),
  ]);

  const apiUptimeSeconds = clampNonNegativeInt(apiStatus?.data?.uptimeSeconds);
  const githubUpdatedAt = activityMonitor.githubUpdatedAt;
  const ankiUpdatedAt = activityMonitor.ankiUpdatedAt;
  const collectorUpdatedAt =
    parseIsoDate(apiStatus?.data?.collector?.lastUpdatedAt ?? null) ??
    [githubUpdatedAt, ankiUpdatedAt]
      .filter((v): v is Date => v instanceof Date)
      .sort((a, b) => a.getTime() - b.getTime())
      .at(-1) ??
    null;
  const upworkerUpdatedAt = parseIsoDate(apiStatus?.data?.upworker?.lastFetchedAt ?? null);

  const workerFreshnessMs = 24 * 60 * 60 * 1000;
  const githubCheckStatus = statusFromFreshness(githubUpdatedAt, workerFreshnessMs);
  const ankiCheckStatus = statusFromFreshness(ankiUpdatedAt, workerFreshnessMs);
  const upworkerCheckStatus = statusFromFreshness(upworkerUpdatedAt, workerFreshnessMs);

  const services: ServiceProbe[] = [
    {
      id: 'web',
      status: webProbe.ok ? 'healthy' : 'degraded',
      detail: webProbe.ok ? 'Astro runtime responding' : 'Web health check failed',
      latencyMs: webProbe.latencyMs,
    },
    {
      id: 'api',
      status: apiProbe.ok ? 'healthy' : 'degraded',
      detail: apiProbe.ok ? 'Hono endpoint reachable' : 'API health check failed',
      latencyMs: apiProbe.latencyMs,
    },
    {
      id: 'collector',
      status: combineStatuses([githubCheckStatus, ankiCheckStatus]),
      detail: collectorUpdatedAt ? 'Collector tasks reported recently' : 'Collector has no recent report',
      latencyMs: null,
      checks: [
        {
          id: 'github',
          label: 'GitHub collector',
          status: githubCheckStatus,
          updatedAt: githubUpdatedAt ? githubUpdatedAt.toISOString() : null,
        },
        {
          id: 'anki',
          label: 'Anki collector',
          status: ankiCheckStatus,
          updatedAt: ankiUpdatedAt ? ankiUpdatedAt.toISOString() : null,
        },
      ],
    },
    {
      id: 'upworker',
      status: upworkerCheckStatus,
      detail: upworkerUpdatedAt ? 'Upworker stream is active' : 'Upworker has no run record',
      latencyMs: null,
      checks: [
        {
          id: 'jobs',
          label: 'Jobs stream',
          status: upworkerCheckStatus,
          updatedAt: upworkerUpdatedAt ? upworkerUpdatedAt.toISOString() : null,
        },
      ],
    },
    {
      id: 'db',
      status: activityMonitor.ok ? 'healthy' : 'degraded',
      detail: activityMonitor.ok ? 'Redis-backed activity read OK' : 'Data-plane read failed',
      latencyMs: activityMonitor.latencyMs,
    },
  ];

  return new Response(
    JSON.stringify({
      data: {
        overallStatus: overallStatus(services),
        checkedAt: new Date().toISOString(),
        apiUptimeSeconds,
        services,
      },
      meta: {
        ts: new Date().toISOString(),
      },
    }),
    {
      status: 200,
      headers: {
        'content-type': 'application/json',
        'cache-control': 'no-store',
      },
    },
  );
};
