import { describe, expect, it } from 'vitest';

import { activityMonitorDataSchema, parseApiEnvelope, redisKeys } from './dashboard.js';

describe('dashboard schema', () => {
  it('parses an activity monitor envelope', () => {
    const parsed = parseApiEnvelope(
      {
        data: {
          github: {
            source: 'github',
            label: 'GitHub',
            cells: [{ date: '2026-03-08', level: 2, count: 3 }],
            updatedAt: '2026-03-08T10:00:00.000Z',
          },
          anki: {
            source: 'anki',
            label: 'Anki',
            cells: [{ date: '2026-03-08', level: 4, count: 120 }],
            streak: 7,
            updatedAt: '2026-03-08T10:00:00.000Z',
          },
        },
        meta: { ts: '2026-03-08T10:00:00.000Z', source: 'redis' },
      },
      activityMonitorDataSchema,
    );

    expect(parsed.data.anki.streak).toBe(7);
    expect(parsed.data.github.cells).toHaveLength(1);
  });

  it('builds Redis keys with the shared project convention', () => {
    expect(redisKeys.stat('github', 'default')).toBe('stat:github:default');
    expect(redisKeys.statField('ytmusic', 'track-1', 'analysis')).toBe(
      'stat:ytmusic:track-1:analysis',
    );
  });
});
