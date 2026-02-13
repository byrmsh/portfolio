import { jobDetailSchema, jobLeadSchema, jobRedisRecordSchema, type JobDetail, type JobLead, type JobRedisRecord } from '@portfolio/schema/dashboard';
import { type UpworkJobResult } from '@portfolio/schema/upwork';

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
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

export function upworkJobHref(job: UpworkJobResult): string | undefined {
  const ciphertext = asNonEmptyString(job?.jobTile?.job?.ciphertext);
  if (!ciphertext) return undefined;
  const clean = ciphertext.replace(/^~+/, '');
  return `https://www.upwork.com/jobs/~${encodeURIComponent(clean)}`;
}

export function projectUpworkJobToLead(job: UpworkJobResult, capturedAtIso: string | null): JobLead | null {
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

export function projectUpworkJobToRecord(job: UpworkJobResult, capturedAtIso: string | null): JobRedisRecord | null {
  const base = projectUpworkJobToLead(job, capturedAtIso);
  if (!base) return null;
  const record = {
    ...base,
    description: String(job.description ?? '').trim(),
  };
  const parsed = jobRedisRecordSchema.safeParse(record);
  return parsed.success ? parsed.data : null;
}

export function projectUpworkJobToDetail(job: UpworkJobResult, capturedAtIso: string | null): JobDetail | null {
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

