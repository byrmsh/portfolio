import { describe, expect, it } from 'vitest';

import { normalizePayload } from './system-health';

describe('system health normalization', () => {
  it('maps Prometheus service payloads into the UI contract', () => {
    const normalized = normalizePayload({
      data: {
        checkedAt: '2026-03-08T10:00:00.000Z',
        services: [
          { id: 'web', status: 'healthy', detail: '1/1 ready replicas', metric: '3d' },
          { id: 'api', status: 'healthy', detail: '1/1 ready replicas', metric: '2d' },
          { id: 'db', status: 'partial', detail: '0/1 ready replicas', metric: '0%' },
          {
            id: 'collector',
            status: 'healthy',
            detail: 'Collector cronjobs reported successfully',
            checks: [
              { id: 'github', updatedAt: '2026-03-08T09:00:00.000Z' },
              { id: 'anki', updatedAt: '2026-03-08T08:00:00.000Z' },
            ],
          },
          {
            id: 'lyricist',
            status: 'healthy',
            detail: 'Lyricist cronjobs reported successfully',
            checks: [{ id: 'tracks', updatedAt: '2026-03-08T07:00:00.000Z' }],
          },
          { id: 'argocd', status: 'healthy', detail: '4/4 ready replicas', metric: '12d' },
        ],
      },
      meta: { ts: '2026-03-08T10:00:00.000Z' },
    });

    expect(normalized.data.dragonfly.status).toBe('partial');
    expect(normalized.data.dragonfly.meta).toBe('0%');
    expect(normalized.data.collector.runs).toBe(2);
    expect(normalized.data.collector.meta).toContain('GitHub');
    expect(normalized.checkedAt).toBe('2026-03-08T10:00:00.000Z');
  });
});
