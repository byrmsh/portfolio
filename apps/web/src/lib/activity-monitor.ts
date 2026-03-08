import type {
  ActivityCell,
  ActivityMonitorData,
  ActivitySeries,
} from '@portfolio/schema/dashboard';

export type ActivitySource = 'github' | 'anki';

export const activityColorRamps: Record<ActivitySource, string[]> = {
  github: [
    'bg-[var(--surface-3)] text-[var(--text-muted)] border-[var(--border-subtle)]',
    'bg-emerald-100 text-emerald-950 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-200 dark:border-emerald-900',
    'bg-emerald-200 text-emerald-950 border-emerald-300 dark:bg-emerald-900 dark:text-emerald-100 dark:border-emerald-800',
    'bg-emerald-400 text-white border-emerald-400 dark:bg-emerald-700 dark:text-emerald-50 dark:border-emerald-600',
    'bg-emerald-700 text-white border-emerald-700 dark:bg-emerald-600 dark:text-emerald-50 dark:border-emerald-500',
  ],
  anki: [
    'bg-[var(--surface-3)] text-[var(--text-muted)] border-[var(--border-subtle)]',
    'bg-sky-100 text-sky-950 border-sky-200 dark:bg-sky-950 dark:text-sky-200 dark:border-sky-900',
    'bg-sky-200 text-sky-950 border-sky-300 dark:bg-sky-900 dark:text-sky-100 dark:border-sky-800',
    'bg-sky-400 text-white border-sky-400 dark:bg-sky-700 dark:text-sky-50 dark:border-sky-600',
    'bg-sky-700 text-white border-sky-700 dark:bg-sky-600 dark:text-sky-50 dark:border-sky-500',
  ],
};

export function clampInt(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.trunc(n)));
}

export function activityLevelClass(source: ActivitySource, level: number): string {
  return activityColorRamps[source][clampInt(level ?? 0, 0, 4)];
}

export function parseIsoDateUTC(s: string): Date {
  const [y, m, d] = String(s)
    .split('-')
    .map((v) => Number(v));
  return new Date(Date.UTC(y, (m ?? 1) - 1, d ?? 1));
}

export function last7Cells(series: ActivitySeries | null | undefined): ActivityCell[] {
  const cells = Array.isArray(series?.cells) ? series.cells.slice() : [];
  cells.sort((a, b) => String(a.date).localeCompare(String(b.date)));
  return cells.slice(Math.max(0, cells.length - 7));
}

export function padTo7(cells: ActivityCell[]): ActivityCell[] {
  const out = cells.slice(0, 7);
  while (out.length < 7) out.push({ date: '', count: 0, level: 0 });
  return out;
}

export function emptyActivitySeries(
  source: ActivitySource,
  label: string,
): Pick<ActivitySeries, 'source' | 'label' | 'cells' | 'streak'> {
  return {
    source,
    label,
    cells: [],
    streak: source === 'anki' ? 0 : undefined,
  };
}

export function normalizeActivityMonitorData(
  data: Partial<ActivityMonitorData> | null | undefined,
  labels: Record<ActivitySource, string>,
): ActivityMonitorData {
  return {
    github: data?.github ?? emptyActivitySeries('github', labels.github),
    anki: data?.anki ?? emptyActivitySeries('anki', labels.anki),
  } as ActivityMonitorData;
}

export function findActivityRange(
  githubCells: ActivityCell[],
  ankiCells: ActivityCell[],
): { start: string; end: string } {
  const dates = [...githubCells, ...ankiCells]
    .map((cell) => cell.date)
    .filter((date): date is string => Boolean(date))
    .sort((a, b) => a.localeCompare(b));

  return {
    start: dates[0] ?? '',
    end: dates.at(-1) ?? '',
  };
}
