export type ServiceStatus = 'healthy' | 'partial' | 'degraded' | 'unknown';
export type ServiceKey = 'web' | 'api' | 'argocd' | 'dragonfly' | 'collector' | 'lyricist';

export type StatusNode = {
  status: ServiceStatus;
  latency?: number;
  runs?: number;
  message: string;
  meta?: string;
};

export type SystemHealthStrings = {
  notAvailable: string;
  runSingular: string;
  runPlural: string;
  latencyLabel: string;
  recencyLabel: string;
};

export type ApiStatusResponse = {
  web: StatusNode;
  api: StatusNode;
  argocd: StatusNode;
  dragonfly: StatusNode;
  collector: StatusNode;
  lyricist: StatusNode;
};

export type NormalizedPayload = {
  checkedAt: string | null;
  data: ApiStatusResponse;
};

export const serviceNames: Record<ServiceKey, string> = {
  web: 'apps/web',
  api: 'apps/api',
  collector: 'apps/collector',
  lyricist: 'apps/lyricist',
  dragonfly: 'dragonfly',
  argocd: 'argocd',
};

export const serviceTech: Record<ServiceKey, string> = {
  web: 'Portfolio frontend (Astro)',
  api: 'Portfolio backend API (Hono)',
  collector: 'Personal data collectors',
  lyricist: 'Lyrics analysis worker',
  dragonfly: 'Redis-compatible KV store',
  argocd: 'GitOps control plane',
};

export const serviceOrder: ServiceKey[] = [
  'web',
  'api',
  'collector',
  'lyricist',
  'dragonfly',
  'argocd',
];

export const DEFAULT_DATA: ApiStatusResponse = {
  web: { status: 'unknown', message: '' },
  api: { status: 'unknown', message: '' },
  collector: { status: 'unknown', message: '', runs: 0, meta: '' },
  lyricist: { status: 'unknown', message: '', runs: 0, meta: '' },
  dragonfly: { status: 'unknown', message: '' },
  argocd: { status: 'unknown', message: '' },
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

function metricMinutes(value: string): number | null {
  const trimmed = value.trim().toLowerCase();
  const match = /^(\d+)\s*([mhd])$/.exec(trimmed);
  if (!match) return null;
  const amount = Number(match[1]);
  if (!Number.isFinite(amount) || amount < 0) return null;
  const unit = match[2];
  if (unit === 'm') return amount;
  if (unit === 'h') return amount * 60;
  if (unit === 'd') return amount * 24 * 60;
  return null;
}

export function collectorMetric(meta: string): string | null {
  const github = extractSourceFromMeta(meta, 'github');
  const anki = extractSourceFromMeta(meta, 'anki');
  const githubMinutes = metricMinutes(github);
  const ankiMinutes = metricMinutes(anki);

  if (githubMinutes !== null && ankiMinutes !== null) {
    return githubMinutes <= ankiMinutes ? github : anki;
  }
  if (githubMinutes !== null) return github;
  if (ankiMinutes !== null) return anki;
  return null;
}

export function parseCheckedAt(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null;
  const direct = payload as {
    checkedAt?: unknown;
    data?: { checkedAt?: unknown; timestamp?: unknown };
    meta?: { ts?: unknown };
  };
  return (
    asIso(direct.checkedAt) ??
    asIso(direct.data?.checkedAt) ??
    asIso(direct.data?.timestamp) ??
    asIso(direct.meta?.ts) ??
    null
  );
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

function updatedAtForCheck(
  service: Record<string, unknown> | undefined,
  checkId: string,
): string | null {
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

export function ageMetricFromIso(value: string | null): string | null {
  if (!value) return null;
  const ts = Date.parse(value);
  if (Number.isNaN(ts)) return null;
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
  return `GitHub ${githubAge ?? '--'} • Anki ${ankiAge ?? '--'}`;
}

function sourceFromPayload(payload: unknown): Partial<Record<ServiceKey, Partial<StatusNode>>> {
  if (!payload || typeof payload !== 'object') return {};
  const direct = payload as Partial<Record<ServiceKey, Partial<StatusNode>>> & {
    lyricist?: Partial<StatusNode> & { lastFetchedAt?: unknown };
  };
  if (
    direct.web ||
    direct.api ||
    direct.argocd ||
    direct.dragonfly ||
    direct.collector ||
    direct.lyricist
  ) {
    const lyricistLastFetchedAt = asIso(direct.lyricist?.lastFetchedAt);
    if (lyricistLastFetchedAt) {
      const meta = ageMetricFromIso(lyricistLastFetchedAt) ?? '';
      direct.lyricist = {
        ...direct.lyricist,
        meta,
      };
    }
    return direct;
  }

  const services = (payload as { data?: { services?: Array<Record<string, unknown>> } })?.data
    ?.services;
  if (!Array.isArray(services)) return {};

  const byId = Object.fromEntries(
    services
      .filter((service) => typeof service?.id === 'string')
      .map((service) => [String(service.id), service]),
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
    argocd: {
      status: asStatus(byId.argocd?.status),
      latency: asCount(byId.argocd?.latencyMs),
      message: asText(byId.argocd?.detail, ''),
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
    lyricist: {
      status: asStatus(byId.lyricist?.status),
      runs: runsFromChecks(byId.lyricist),
      message: asText(byId.lyricist?.detail, ''),
      meta: ageMetricFromIso(latestUpdatedAtFromChecks(byId.lyricist)) ?? '',
    },
  };
}

function normalizeStatus(
  source: Partial<Record<ServiceKey, Partial<StatusNode>>>,
): ApiStatusResponse {
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
    argocd: pick('argocd'),
    dragonfly: pick('dragonfly'),
    collector: pick('collector'),
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

export function metricFor(key: ServiceKey, node: StatusNode, strings: SystemHealthStrings): string {
  if (key === 'collector') return collectorMetric(asText(node.meta, '')) ?? strings.notAvailable;
  if (key === 'lyricist') {
    const freshness = asText(node.meta, '');
    if (freshness) return freshness;
    const runs = asCount(node.runs);
    if (runs <= 0) return strings.notAvailable;
    return `${runs} ${runs === 1 ? strings.runSingular : strings.runPlural}`;
  }
  const latency = asCount(node.latency);
  return latency > 0 ? `${latency}ms` : strings.notAvailable;
}

export function metricClass(value: string): string {
  const base = 'min-h-[2.25rem] flex items-end';
  return /\d/.test(value)
    ? `${base} text-3xl font-mono font-medium text-[var(--text-primary)]`
    : `${base} text-3xl font-mono font-medium uppercase tracking-wide text-[var(--text-muted)]`;
}

export function labelFor(key: ServiceKey, strings: SystemHealthStrings): string {
  if (key === 'collector' || key === 'lyricist') return strings.recencyLabel;
  return strings.latencyLabel;
}

export function detailFor(
  _key: ServiceKey,
  _node: StatusNode,
  _strings: SystemHealthStrings,
): string {
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
