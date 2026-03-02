import type { APIRoute } from 'astro';

type ServiceStatus = 'healthy' | 'partial' | 'degraded' | 'unknown';
type ServiceId = 'web' | 'api' | 'argocd' | 'collector' | 'lyricist' | 'db';

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
  metric?: string;
  checks?: ServiceCheck[];
};

type PrometheusQueryResponse = {
  status: 'success' | 'error';
  data?: {
    resultType?: string;
    result?: Array<{
      metric?: Record<string, string>;
      value?: [number, string];
    }>;
  };
};

function parseUnixSeconds(value: number): Date | null {
  if (!Number.isFinite(value) || value <= 0) return null;
  const date = new Date(value * 1000);
  return Number.isNaN(date.getTime()) ? null : date;
}

function statusFromFreshness(
  timestamp: Date | null,
  healthyFreshnessMs: number,
  partialFreshnessMs: number,
): ServiceStatus {
  if (!timestamp) return 'unknown';
  const ageMs = Date.now() - timestamp.getTime();
  if (ageMs <= healthyFreshnessMs) return 'healthy';
  if (ageMs <= partialFreshnessMs) return 'partial';
  return 'degraded';
}

function combineStatuses(statuses: ServiceStatus[]): ServiceStatus {
  if (statuses.some((status) => status === 'degraded')) return 'degraded';
  if (statuses.some((status) => status === 'partial')) return 'partial';
  if (statuses.some((status) => status === 'unknown')) return 'unknown';
  return 'healthy';
}

function statusFromReplicaAvailability(available: number, desired: number): ServiceStatus {
  if (!Number.isFinite(available) || !Number.isFinite(desired) || desired <= 0) return 'unknown';
  if (available >= desired) return 'healthy';
  if (available > 0) return 'partial';
  return 'degraded';
}

function asMetricPercent(available: number, desired: number): string {
  if (!Number.isFinite(available) || !Number.isFinite(desired) || desired <= 0) return 'n/a';
  const ratio = Math.max(0, Math.min(1, available / desired));
  return `${Math.round(ratio * 100)}%`;
}

function asAgeMetricFromSeconds(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return 'n/a';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${Math.max(1, minutes)}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function parsePromValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

async function queryPrometheusVector(
  prometheusUrl: string,
  query: string,
  timeoutMs: number,
): Promise<Array<{ metric: Record<string, string>; value: number }> | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const requestUrl = new URL(`${prometheusUrl.replace(/\/$/, '')}/api/v1/query`);
    requestUrl.searchParams.set('query', query);
    const response = await fetch(requestUrl, {
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal,
      headers: { accept: 'application/json' },
    });
    if (!response.ok) return null;
    const payload = (await response.json()) as PrometheusQueryResponse;
    if (payload.status !== 'success' || payload.data?.resultType !== 'vector') return null;
    const result = payload.data.result ?? [];
    return result
      .map((entry) => {
        const value = parsePromValue(entry.value?.[1]);
        if (value === null) return null;
        return {
          metric: entry.metric ?? {},
          value,
        };
      })
      .filter(
        (entry): entry is { metric: Record<string, string>; value: number } => entry !== null,
      );
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function overallStatus(services: ServiceProbe[]): ServiceStatus {
  if (services.some((service) => service.status === 'degraded')) return 'degraded';
  if (services.some((service) => service.status === 'unknown')) return 'unknown';
  if (services.some((service) => service.status === 'partial')) return 'partial';
  return 'healthy';
}

function valueForLabel(
  samples: Array<{ metric: Record<string, string>; value: number }> | null,
  label: string,
  value: string,
): number | null {
  if (!samples) return null;
  const sample = samples.find((entry) => entry.metric[label] === value);
  return sample?.value ?? null;
}

function firstValue(
  samples: Array<{ metric: Record<string, string>; value: number }> | null,
): number | null {
  if (!samples || samples.length === 0) return null;
  return samples[0]?.value ?? null;
}

async function buildDeploymentProbe(
  prometheusUrl: string,
  options: {
    id: Extract<ServiceId, 'web' | 'api' | 'db'>;
    namespace: string;
    deployment: string;
    label: string;
  },
): Promise<ServiceProbe> {
  const podPattern = `${options.deployment}-.*`;
  const [availableSeries, desiredSeries, uptimeSeries] = await Promise.all([
    queryPrometheusVector(
      prometheusUrl,
      `kube_deployment_status_replicas_available{namespace="${options.namespace}",deployment="${options.deployment}"}`,
      1800,
    ),
    queryPrometheusVector(
      prometheusUrl,
      `kube_deployment_spec_replicas{namespace="${options.namespace}",deployment="${options.deployment}"}`,
      1800,
    ),
    queryPrometheusVector(
      prometheusUrl,
      `min(time() - kube_pod_start_time{namespace="${options.namespace}",pod=~"${podPattern}"})`,
      1800,
    ),
  ]);

  const available = valueForLabel(availableSeries, 'deployment', options.deployment);
  const desired = valueForLabel(desiredSeries, 'deployment', options.deployment);
  if (available === null || desired === null) {
    return {
      id: options.id,
      status: 'unknown',
      detail: `${options.label} replica metrics unavailable`,
      latencyMs: null,
      metric: 'n/a',
    };
  }

  const availableRounded = Math.max(0, Math.floor(available));
  const desiredRounded = Math.max(0, Math.floor(desired));
  const uptimeSeconds = firstValue(uptimeSeries);
  const uptimeMetric =
    uptimeSeconds !== null
      ? asAgeMetricFromSeconds(uptimeSeconds)
      : asMetricPercent(availableRounded, desiredRounded);

  return {
    id: options.id,
    status: statusFromReplicaAvailability(availableRounded, desiredRounded),
    detail: `${availableRounded}/${desiredRounded} ready replicas`,
    latencyMs: null,
    metric: uptimeMetric,
  };
}

async function buildArgocdProbe(prometheusUrl: string): Promise<ServiceProbe> {
  const [availableSeries, desiredSeries, uptimeSeries] = await Promise.all([
    queryPrometheusVector(
      prometheusUrl,
      'sum(kube_deployment_status_replicas_available{namespace="argocd",deployment=~"argocd-.*"})',
      1800,
    ),
    queryPrometheusVector(
      prometheusUrl,
      'sum(kube_deployment_spec_replicas{namespace="argocd",deployment=~"argocd-.*"})',
      1800,
    ),
    queryPrometheusVector(
      prometheusUrl,
      'min(time() - kube_pod_start_time{namespace="argocd",pod=~"argocd-.*"})',
      1800,
    ),
  ]);

  const available = firstValue(availableSeries);
  const desired = firstValue(desiredSeries);
  if (available === null || desired === null) {
    return {
      id: 'argocd',
      status: 'unknown',
      detail: 'Argo CD replica metrics unavailable',
      latencyMs: null,
      metric: 'n/a',
    };
  }

  const availableRounded = Math.max(0, Math.floor(available));
  const desiredRounded = Math.max(0, Math.floor(desired));
  const uptimeSeconds = firstValue(uptimeSeries);
  return {
    id: 'argocd',
    status: statusFromReplicaAvailability(availableRounded, desiredRounded),
    detail: `${availableRounded}/${desiredRounded} ready replicas`,
    latencyMs: null,
    metric:
      uptimeSeconds !== null
        ? asAgeMetricFromSeconds(uptimeSeconds)
        : asMetricPercent(availableRounded, desiredRounded),
  };
}

async function queryCronjobLastSuccess(
  prometheusUrl: string,
  cronRegex: string,
): Promise<Array<{ cronjob: string; updatedAt: Date | null }>> {
  const samples = await queryPrometheusVector(
    prometheusUrl,
    `kube_cronjob_status_last_successful_time{namespace="portfolio",cronjob=~"${cronRegex}"}`,
    2000,
  );
  if (!samples) return [];

  return samples.map((sample) => {
    const cronjob = sample.metric.cronjob ?? '';
    const updatedAt = parseUnixSeconds(sample.value);
    return { cronjob, updatedAt };
  });
}

export const GET: APIRoute = async () => {
  const prometheusUrl =
    process.env.PROMETHEUS_URL ??
    import.meta.env.PROMETHEUS_URL ??
    import.meta.env.PUBLIC_PROMETHEUS_URL ??
    'http://grafana-stack-kube-prometh-prometheus.monitoring.svc.cluster.local:9090';

  const [webProbe, apiProbe, dbProbe, argocdProbe, collectorCronjobs, lyricistCronjobs] =
    await Promise.all([
      buildDeploymentProbe(prometheusUrl, {
        id: 'web',
        namespace: 'portfolio',
        deployment: 'web-deployment',
        label: 'Web',
      }),
      buildDeploymentProbe(prometheusUrl, {
        id: 'api',
        namespace: 'portfolio',
        deployment: 'api-deployment',
        label: 'API',
      }),
      buildDeploymentProbe(prometheusUrl, {
        id: 'db',
        namespace: 'portfolio',
        deployment: 'db-deployment',
        label: 'Dragonfly',
      }),
      buildArgocdProbe(prometheusUrl),
      queryCronjobLastSuccess(prometheusUrl, 'collector-(github|anki)-cronjob'),
      queryCronjobLastSuccess(prometheusUrl, 'lyricist-(sync|analysis)-cronjob'),
    ]);

  const collectorByName = Object.fromEntries(
    collectorCronjobs.map((entry) => [entry.cronjob, entry.updatedAt]),
  ) as Record<string, Date | null>;
  const lyricistByName = Object.fromEntries(
    lyricistCronjobs.map((entry) => [entry.cronjob, entry.updatedAt]),
  ) as Record<string, Date | null>;

  const healthyFreshnessMs = 24 * 60 * 60 * 1000;
  const partialFreshnessMs = 48 * 60 * 60 * 1000;

  const githubUpdatedAt = collectorByName['collector-github-cronjob'] ?? null;
  const ankiUpdatedAt = collectorByName['collector-anki-cronjob'] ?? null;
  const githubCheckStatus = statusFromFreshness(
    githubUpdatedAt,
    healthyFreshnessMs,
    partialFreshnessMs,
  );
  const ankiCheckStatus = statusFromFreshness(
    ankiUpdatedAt,
    healthyFreshnessMs,
    partialFreshnessMs,
  );
  const collectorStatus = combineStatuses([githubCheckStatus, ankiCheckStatus]);
  const collectorHasAnyData = githubUpdatedAt instanceof Date || ankiUpdatedAt instanceof Date;

  const lyricistSyncUpdatedAt = lyricistByName['lyricist-sync-cronjob'] ?? null;
  const lyricistAnalyzeUpdatedAt = lyricistByName['lyricist-analysis-cronjob'] ?? null;
  const lyricistSyncStatus = statusFromFreshness(
    lyricistSyncUpdatedAt,
    healthyFreshnessMs,
    partialFreshnessMs,
  );
  const lyricistAnalyzeStatus = statusFromFreshness(
    lyricistAnalyzeUpdatedAt,
    healthyFreshnessMs,
    partialFreshnessMs,
  );
  const lyricistStatus = combineStatuses([lyricistSyncStatus, lyricistAnalyzeStatus]);
  const lyricistLastUpdatedAt =
    [lyricistSyncUpdatedAt, lyricistAnalyzeUpdatedAt]
      .filter((value): value is Date => value instanceof Date)
      .sort((a, b) => b.getTime() - a.getTime())
      .at(0) ?? null;

  const services: ServiceProbe[] = [
    webProbe,
    apiProbe,
    argocdProbe,
    {
      id: 'collector',
      status: collectorStatus,
      detail: collectorHasAnyData
        ? 'Collector cronjobs reported successfully'
        : 'Collector cronjobs have no success timestamp yet',
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
      id: 'lyricist',
      status: lyricistStatus,
      detail: lyricistLastUpdatedAt
        ? 'Lyricist cronjobs reported successfully'
        : 'Lyricist cronjobs have no success timestamp yet',
      latencyMs: null,
      checks: [
        {
          id: 'tracks',
          label: 'Track analysis',
          status: lyricistStatus,
          updatedAt: lyricistLastUpdatedAt ? lyricistLastUpdatedAt.toISOString() : null,
        },
      ],
    },
    dbProbe,
  ];

  return new Response(
    JSON.stringify({
      data: {
        overallStatus: overallStatus(services),
        checkedAt: new Date().toISOString(),
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
