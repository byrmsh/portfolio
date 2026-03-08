import { describe, expect, it } from 'vitest';

import {
  activityLevelClass,
  findActivityRange,
  normalizeActivityMonitorData,
  padTo7,
} from './activity-monitor';

describe('activity monitor helpers', () => {
  it('fills missing sources with empty defaults', () => {
    const data = normalizeActivityMonitorData(
      {
        anki: {
          source: 'anki',
          label: 'Anki',
          cells: [{ date: '2026-03-08', count: 10, level: 2 }],
          streak: 4,
          updatedAt: '2026-03-08T10:00:00.000Z',
        },
      },
      { github: 'GitHub', anki: 'Anki' },
    );

    expect(data.github.source).toBe('github');
    expect(data.github.cells).toEqual([]);
    expect(data.anki.streak).toBe(4);
  });

  it('derives the visible range from padded cells', () => {
    const githubCells = padTo7([{ date: '2026-03-02', count: 1, level: 1 }]);
    const ankiCells = padTo7([{ date: '2026-03-08', count: 12, level: 4 }]);

    expect(findActivityRange(githubCells, ankiCells)).toEqual({
      start: '2026-03-02',
      end: '2026-03-08',
    });
  });

  it('maps activity intensity to a stable class ramp', () => {
    expect(activityLevelClass('github', 9)).toContain('bg-emerald-700');
    expect(activityLevelClass('anki', -4)).toContain('bg-[var(--surface-3)]');
  });
});
