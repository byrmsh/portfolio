type JobsCursor = { page: number; offset: number };

function clampInt(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.trunc(n)));
}

export function decodeJobsCursor(raw: string | null): JobsCursor {
  if (!raw) return { page: 1, offset: 0 };
  const trimmed = raw.trim();
  if (/^\\d+$/.test(trimmed)) return { page: clampInt(Number(trimmed), 1, 100000), offset: 0 };

  try {
    const json = Buffer.from(trimmed, 'base64url').toString('utf8');
    const parsed = JSON.parse(json) as { page?: unknown; offset?: unknown };
    const page = typeof parsed.page === 'number' ? clampInt(parsed.page, 1, 100000) : 1;
    const offset = typeof parsed.offset === 'number' ? clampInt(parsed.offset, 0, 500) : 0;
    return { page, offset };
  } catch {
    return { page: 1, offset: 0 };
  }
}

export function encodeJobsCursor(cur: JobsCursor): string {
  return Buffer.from(JSON.stringify(cur), 'utf8').toString('base64url');
}

type JobLead = {
  id: string;
  source: 'public';
  title: string;
  summary: string;
  tags: string[];
  publishedAt: string;
  capturedAt: string;
  href?: string;
  companyName?: string;
  location?: string;
  remote?: boolean;
  jobTypes?: string[];
};

type JobDetail = JobLead & {
  description: string;
};

type JobBoardJob = {
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
  return `${clean.slice(0, Math.max(0, maxLen - 3)).trim()}...`;
}

function parseIso(value: string): string | null {
  const ts = Date.parse(value);
  if (Number.isNaN(ts)) return null;
  return new Date(ts).toISOString();
}

function parseJobBoardJob(value: unknown): JobBoardJob | null {
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

function projectToDetail(job: JobBoardJob, capturedAtIso: string): JobDetail {
  const publishedAt = parseIso(job.created_at) ?? capturedAtIso;
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

  return {
    id: job.slug,
    source: 'public',
    title: job.title.trim(),
    summary: summarize(cleanText, 180),
    description: cleanText,
    tags: tags.length ? tags : ['Job'],
    publishedAt,
    capturedAt: publishedAt,
    href: job.url,
    companyName: job.company_name.trim(),
    location: job.location.trim() || undefined,
    remote: job.remote,
    jobTypes: job.job_types.length ? job.job_types : undefined,
  };
}

async function fetchWithTimeout(url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { headers: { accept: 'application/json' }, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

export async function fetchJobsPageFromUpstream(opts: {
  limit: number;
  before: string | null;
}): Promise<{ items: JobLead[]; nextCursor: string | null }> {
  const cursor = decodeJobsCursor(opts.before);
  const capturedAtIso = new Date().toISOString();

  let rows: unknown[] = [];
  let hasNext = false;
  try {
    const res = await fetchWithTimeout(
      `https://www.arbeitnow.com/api/job-board-api?page=${cursor.page}`,
      10_000,
    );
    const json = (await res.json()) as { data?: unknown; links?: { next?: unknown } | null };
    rows = Array.isArray(json?.data) ? (json.data as unknown[]) : [];
    hasNext = Boolean(json?.links && (json.links as { next?: unknown }).next);
  } catch {
    rows = [];
    hasNext = false;
  }

  const parsed = rows.map(parseJobBoardJob).filter((v): v is JobBoardJob => !!v);
  const slice = parsed.slice(cursor.offset, cursor.offset + opts.limit);

  const items: JobLead[] = slice.map((j) => {
    const detail = projectToDetail(j, capturedAtIso);
    const { description: _desc, ...lead } = detail;
    return lead;
  });

  const nextOffset = cursor.offset + slice.length;
  const nextCursor =
    slice.length === 0
      ? null
      : nextOffset < parsed.length
        ? encodeJobsCursor({ page: cursor.page, offset: nextOffset })
        : hasNext
          ? encodeJobsCursor({ page: cursor.page + 1, offset: 0 })
          : null;

  return { items, nextCursor };
}

export async function fetchJobDetailFromUpstream(opts: {
  id: string;
  cursor: string | null;
}): Promise<JobDetail | null> {
  const capturedAtIso = new Date().toISOString();
  const cursorPage = opts.cursor ? decodeJobsCursor(opts.cursor).page : null;
  const startPage = clampInt(cursorPage || 1, 1, 100000);
  const maxPages = 5;

  try {
    for (let p = startPage; p < startPage + maxPages; p += 1) {
      const res = await fetchWithTimeout(`https://www.arbeitnow.com/api/job-board-api?page=${p}`, 10_000);
      const json = (await res.json()) as { data?: unknown };
      const rows = Array.isArray(json?.data) ? (json.data as unknown[]) : [];
      const parsed = rows.map(parseJobBoardJob).filter((v): v is JobBoardJob => !!v);
      const found = parsed.find((j) => j.slug === opts.id);
      if (!found) continue;
      return projectToDetail(found, capturedAtIso);
    }
  } catch {
    // fall through
  }

  return null;
}
