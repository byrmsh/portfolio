export type ServiceStatus = 'healthy' | 'partial' | 'degraded' | 'unknown';
export type ServiceKey = 'web' | 'api' | 'dragonfly' | 'collector' | 'upworker' | 'lyricist';

export type StatusNode = {
  status: ServiceStatus;
  latency?: number;
  runs?: number;
  message: string;
  meta?: string;
};

export type ApiStatusResponse = {
  web: StatusNode;
  api: StatusNode;
  dragonfly: StatusNode;
  collector: StatusNode;
  upworker: StatusNode;
  lyricist: StatusNode;
};

export type NormalizedPayload = {
  checkedAt: string | null;
  data: ApiStatusResponse;
};

export const serviceNames: Record<ServiceKey, string> = {
  web: 'apps/web',
  api: 'apps/api',
  dragonfly: 'dragonfly',
  collector: 'apps/collector',
  upworker: 'apps/upworker',
  lyricist: 'apps/lyricist',
};

export const serviceTech: Record<ServiceKey, string> = {
  web: 'Portfolio frontend (Astro)',
  api: 'Portfolio backend API (Hono)',
  collector: 'Personal data collectors',
  upworker: 'Upwork ingestion worker',
  lyricist: 'Lyrics analysis worker',
  dragonfly: 'Redis-compatible KV store',
};

export const serviceOrder: ServiceKey[] = ['web', 'api', 'collector', 'upworker', 'lyricist', 'dragonfly'];

export const DEFAULT_DATA: ApiStatusResponse = {
  web: { status: 'unknown', message: '' },
  api: { status: 'unknown', message: '' },
  dragonfly: { status: 'unknown', message: '' },
  collector: { status: 'unknown', message: '', runs: 0, meta: '' },
  upworker: { status: 'unknown', message: '', runs: 0, meta: '' },
  lyricist: { status: 'unknown', message: '', runs: 0, meta: '' },
};

export function asStatus(value: unknown): ServiceStatus {
  return value === 'healthy' || value === 'partial' || value === 'degraded' ? value : 'unknown';
}

export function asCount(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.floor(value));
}

export function asText(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim().length > 0 ? value : fallback;
}

export function asIso(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  return Number.isNaN(Date.parse(value)) ? null : value;
}

function extractSourceFromMeta(meta: string, source: 'github' | 'anki'): string {
  const pattern = source === 'github' ? /github\s+([^•]+)/i : /anki\s+([^•]+)/i;
  const match = pattern.exec(meta);
  if (!match) return '--';
  return match[1].replace(/ago/gi, '').trim() || '--';
}

export function collectorMetric(meta: string): string {
  const github = extractSourceFromMeta(meta, 'github');
  const anki = extractSourceFromMeta(meta, 'anki');
  if (github !== '--') return github;
  if (anki !== '--') return anki;
  return 'N/A';
}

export function parseCheckedAt(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null;
  const direct = payload as {
    checkedAt?: unknown;
    data?: { checkedAt?: unknown; timestamp?: unknown };
    meta?: { ts?: unknown };
  };
  return asIso(direct.checkedAt) ?? asIso(direct.data?.checkedAt) ?? asIso(direct.data?.timestamp) ?? asIso(direct.meta?.ts) ?? null;
}

function latestUpdatedAtFromChecks(service: Record<string, unknown> | undefined): string | null {
  const checks = service?.checks;
  if (!Array.isArray(checks)) return null;
  for (const check of checks) {
    if (!check || typeof check !== 'object') continue;
    const updatedAt = (check as { updatedAt?: unknown }).updatedAt;
    if (typeof updatedAt === 'string' && updatedAt.length > 0) return updatedAt;
  }
  return null;
}

function updatedAtForCheck(service: Record<string, unknown> | undefined, checkId: string): string | null {
  const checks = service?.checks;
  if (!Array.isArray(checks)) return null;
  for (const check of checks) {
    if (!check || typeof check !== 'object') continue;
    const id = (check as { id?: unknown }).id;
    const updatedAt = (check as { updatedAt?: unknown }).updatedAt;
    if (id === checkId && typeof updatedAt === 'string' && updatedAt.length > 0) return updatedAt;
  }
  return null;
}

export function ageMetricFromIso(value: string | null): string {
  if (!value) return 'N/A';
  const ts = Date.parse(value);
  if (Number.isNaN(ts)) return 'N/A';
  const ageMs = Math.max(0, Date.now() - ts);
  const minutes = Math.floor(ageMs / 60000);
  if (minutes < 60) return `${Math.max(1, minutes)}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function collectorMetaFromChecks(service: Record<string, unknown> | undefined): string {
  const githubAge = ageMetricFromIso(updatedAtForCheck(service, 'github'));
  const ankiAge = ageMetricFromIso(updatedAtForCheck(service, 'anki'));
  return `GitHub ${githubAge === 'N/A' ? '--' : githubAge} • Anki ${ankiAge === 'N/A' ? '--' : ankiAge}`;
}

function sourceFromPayload(payload: unknown): Partial<Record<ServiceKey, Partial<StatusNode>>> {
  if (!payload || typeof payload !== 'object') return {};
  const direct = payload as Partial<Record<ServiceKey, Partial<StatusNode>>> & {
    upworker?: Partial<StatusNode> & { lastFetchedAt?: unknown };
    lyricist?: Partial<StatusNode> & { lastFetchedAt?: unknown };
  };
  if (direct.web || direct.api || direct.dragonfly || direct.collector || direct.upworker || direct.lyricist) {
    const upworkerLastFetchedAt = asIso(direct.upworker?.lastFetchedAt);
    if (upworkerLastFetchedAt) {
      direct.upworker = {
        ...direct.upworker,
        meta: ageMetricFromIso(upworkerLastFetchedAt),
      };
    }
    const lyricistLastFetchedAt = asIso(direct.lyricist?.lastFetchedAt);
    if (lyricistLastFetchedAt) {
      direct.lyricist = {
        ...direct.lyricist,
        meta: ageMetricFromIso(lyricistLastFetchedAt),
      };
    }
    return direct;
  }

  const services = (payload as { data?: { services?: Array<Record<string, unknown>> } })?.data?.services;
  if (!Array.isArray(services)) return {};

  const byId = Object.fromEntries(
    services.filter((service) => typeof service?.id === 'string').map((service) => [String(service.id), service]),
  ) as Record<string, Record<string, unknown>>;

  const runsFromChecks = (service: Record<string, unknown> | undefined): number => {
    const checks = service?.checks;
    if (!Array.isArray(checks)) return 0;
    return checks.filter((check) => {
      if (!check || typeof check !== 'object') return false;
      const updatedAt = (check as { updatedAt?: unknown }).updatedAt;
      return typeof updatedAt === 'string' && updatedAt.length > 0;
    }).length;
  };

  return {
    web: {
      status: asStatus(byId.web?.status),
      latency: asCount(byId.web?.latencyMs),
      message: asText(byId.web?.detail, ''),
    },
    api: {
      status: asStatus(byId.api?.status),
      latency: asCount(byId.api?.latencyMs),
      message: asText(byId.api?.detail, ''),
    },
    dragonfly: {
      status: asStatus(byId.db?.status),
      latency: asCount(byId.db?.latencyMs),
      message: asText(byId.db?.detail, ''),
    },
    collector: {
      status: asStatus(byId.collector?.status),
      runs: runsFromChecks(byId.collector),
      message: asText(byId.collector?.detail, ''),
      meta: collectorMetaFromChecks(byId.collector),
    },
    upworker: {
      status: asStatus(byId.upworker?.status),
      runs: runsFromChecks(byId.upworker),
      message: asText(byId.upworker?.detail, ''),
      meta: ageMetricFromIso(latestUpdatedAtFromChecks(byId.upworker)),
    },
    lyricist: {
      status: asStatus(byId.lyricist?.status),
      runs: runsFromChecks(byId.lyricist),
      message: asText(byId.lyricist?.detail, ''),
      meta: ageMetricFromIso(latestUpdatedAtFromChecks(byId.lyricist)),
    },
  };
}

function normalizeStatus(source: Partial<Record<ServiceKey, Partial<StatusNode>>>): ApiStatusResponse {
  const pick = (key: ServiceKey): StatusNode => {
    const fallback = DEFAULT_DATA[key];
    const raw = source[key] ?? {};
    return {
      status: asStatus(raw.status ?? fallback.status),
      latency: asCount(raw.latency ?? fallback.latency ?? 0),
      runs: asCount(raw.runs ?? fallback.runs ?? 0),
      message: asText(raw.message, fallback.message),
      meta: asText(raw.meta, fallback.meta ?? ''),
    };
  };

  return {
    web: pick('web'),
    api: pick('api'),
    dragonfly: pick('dragonfly'),
    collector: pick('collector'),
    upworker: pick('upworker'),
    lyricist: pick('lyricist'),
  };
}

export function normalizePayload(payload: unknown): NormalizedPayload {
  return {
    checkedAt: parseCheckedAt(payload),
    data: normalizeStatus(sourceFromPayload(payload)),
  };
}

export function dotClass(status: ServiceStatus): string {
  return status === 'healthy' ? 'bg-emerald-500' : 'bg-rose-500';
}

export function metricFor(key: ServiceKey, node: StatusNode): string {
  if (key === 'collector') return collectorMetric(asText(node.meta, ''));
  if (key === 'upworker' || key === 'lyricist') {
    const freshness = asText(node.meta, 'N/A');
    if (freshness !== 'N/A') return freshness;
    const runs = asCount(node.runs);
    return runs > 0 ? `${runs} run${runs === 1 ? '' : 's'}` : 'N/A';
  }
  const latency = asCount(node.latency);
  return latency > 0 ? `${latency}ms` : 'N/A';
}

export function metricClass(value: string): string {
  const base = 'min-h-[2.25rem] flex items-end';
  return /\d/.test(value)
    ? `${base} text-3xl font-mono font-medium text-neutral-900`
    : `${base} text-3xl font-mono font-medium uppercase tracking-wide text-neutral-300`;
}

export function labelFor(key: ServiceKey): string {
  if (key === 'collector' || key === 'upworker' || key === 'lyricist') return 'RECENCY';
  return 'LATENCY';
}

export function detailFor(key: ServiceKey, node: StatusNode): string {
  if (key === 'upworker') return /active/i.test(node.message) ? 'Jobs stream active' : '';
  return '';
}

export function formatCheckedValue(checkedAt: string | null): string {
  if (!checkedAt) return '--:--:--';
  const date = new Date(checkedAt);
  if (Number.isNaN(date.getTime())) return '--:--:--';
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
}
