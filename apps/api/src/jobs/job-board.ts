import {
  jobDetailSchema,
  jobLeadSchema,
  jobRedisRecordSchema,
  type JobDetail,
  type JobLead,
  type JobRedisRecord,
} from '@portfolio/schema/dashboard';

export type JobBoardJob = {
  slug: string;
  company_name: string;
  title: string;
  description: string;
  remote: boolean;
  url: string;
  tags: string[];
  job_types: string[];
  location: string;
  created_at: string;
};

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function uniq(values: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const v of values) {
    if (seen.has(v)) continue;
    seen.add(v);
    out.push(v);
  }
  return out;
}

function decodeHtmlEntities(text: string): string {
  // Minimal decode for common entities we expect in job descriptions.
  return text
    .replaceAll('&amp;', '&')
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .replaceAll('&quot;', '"')
    .replaceAll('&#39;', "'")
    .replace(/&#(\d+);/g, (_, n) => {
      const code = Number(n);
      if (!Number.isFinite(code) || code <= 0 || code > 0x10ffff) return _;
      try {
        return String.fromCodePoint(code);
      } catch {
        return _;
      }
    });
}

function htmlToText(html: string): string {
  // The upstream job board API returns HTML; convert to readable plain text for the site UI.
  const withBreaks = html
    .replace(/<\s*br\s*\/?>/gi, '\n')
    .replace(/<\s*\/p\s*>/gi, '\n\n')
    .replace(/<\s*\/li\s*>/gi, '\n')
    .replace(/<\s*li\s*>/gi, '- ');

  const stripped = withBreaks.replace(/<[^>]+>/g, '');
  return decodeHtmlEntities(stripped)
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function summarize(text: string, maxLen: number): string {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (clean.length <= maxLen) return clean;
  return `${clean.slice(0, Math.max(0, maxLen - 1)).trim()}…`;
}

function parseIso(value: string): string | null {
  const ts = Date.parse(value);
  if (Number.isNaN(ts)) return null;
  return new Date(ts).toISOString();
}

export function parseJobBoardJob(value: unknown): JobBoardJob | null {
  if (!value || typeof value !== 'object') return null;
  const v = value as Record<string, unknown>;

  const slug = asNonEmptyString(v.slug);
  const company_name = asNonEmptyString(v.company_name);
  const title = asNonEmptyString(v.title);
  const description = asNonEmptyString(v.description);
  const url = asNonEmptyString(v.url);
  const location = asNonEmptyString(v.location) ?? '';
  const created_at = asNonEmptyString(v.created_at) ?? '';
  const remote = typeof v.remote === 'boolean' ? v.remote : false;
  const tags = Array.isArray(v.tags)
    ? v.tags.map(asNonEmptyString).filter((t): t is string => t !== null)
    : [];
  const job_types = Array.isArray(v.job_types)
    ? v.job_types.map(asNonEmptyString).filter((t): t is string => t !== null)
    : [];

  if (!slug || !company_name || !title || !description || !url) return null;

  return {
    slug,
    company_name,
    title,
    description,
    remote,
    url,
    tags,
    job_types,
    location,
    created_at,
  };
}

export function projectJobBoardJobToLead(job: JobBoardJob, capturedAtIso: string): JobLead | null {
  const publishedAt = parseIso(job.created_at) ?? capturedAtIso;
  const capturedAt = publishedAt;
  const cleanText = htmlToText(job.description);

  const tags = uniq([
    ...job.tags,
    ...job.job_types,
    job.remote ? 'Remote' : '',
    job.location || '',
    job.company_name,
  ])
    .map((t) => t.trim())
    .filter((t) => t.length > 0)
    .slice(0, 6);

  const lead = {
    id: job.slug,
    source: 'public' as const,
    title: job.title.trim(),
    summary: summarize(cleanText, 180),
    tags: tags.length ? tags : ['Job'],
    publishedAt,
    capturedAt,
    href: job.url,
    companyName: job.company_name.trim(),
    location: job.location.trim() || undefined,
    remote: job.remote,
    jobTypes: job.job_types.length ? job.job_types : undefined,
  };

  const parsed = jobLeadSchema.safeParse(lead);
  return parsed.success ? parsed.data : null;
}

export function projectJobBoardJobToRecord(
  job: JobBoardJob,
  capturedAtIso: string,
): JobRedisRecord | null {
  const base = projectJobBoardJobToLead(job, capturedAtIso);
  if (!base) return null;

  const record = {
    ...base,
    description: htmlToText(job.description),
  };
  const parsed = jobRedisRecordSchema.safeParse(record);
  return parsed.success ? parsed.data : null;
}

export function projectJobBoardJobToDetail(
  job: JobBoardJob,
  capturedAtIso: string,
): JobDetail | null {
  const parsed = projectJobBoardJobToRecord(job, capturedAtIso);
  if (!parsed) return null;
  const detail = { ...parsed };
  const validated = jobDetailSchema.safeParse(detail);
  return validated.success ? validated.data : null;
}
