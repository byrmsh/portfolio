import { beforeEach, describe, expect, it, vi } from 'vitest';

const redisMock = {
  get: vi.fn(),
  ping: vi.fn(),
  zrevrange: vi.fn(),
  zcard: vi.fn(),
  pipeline: vi.fn(() => ({
    get: vi.fn().mockReturnThis(),
    exec: vi.fn().mockResolvedValue([]),
  })),
};

vi.mock('ioredis', () => ({
  Redis: vi.fn(() => redisMock),
}));

const { default: app } = await import('./index.js');

describe('api routes', () => {
  beforeEach(() => {
    redisMock.get.mockReset();
    redisMock.ping.mockReset();
    redisMock.zrevrange.mockReset();
    redisMock.zcard.mockReset();
    redisMock.pipeline.mockClear();
  });

  it('returns empty activity data when Redis has not been populated yet', async () => {
    redisMock.get.mockResolvedValue(null);

    const response = await app.request('http://localhost/api/activity-monitor');
    const payload = (await response.json()) as {
      data: {
        github: { cells: Array<unknown> };
        anki: { cells: Array<unknown>; streak?: number };
      };
    };

    expect(response.status).toBe(200);
    expect(payload.data.github.cells).toHaveLength(7);
    expect(payload.data.anki.cells).toHaveLength(7);
    expect(payload.data.anki.streak).toBe(0);
  });

  it('marks Dragonfly degraded when the Redis ping fails', async () => {
    redisMock.get.mockResolvedValue(null);
    redisMock.ping.mockRejectedValue(new Error('unreachable'));

    const response = await app.request('http://localhost/api/status');
    const payload = (await response.json()) as {
      dragonfly: { status: string };
      collector: { runs: number };
    };

    expect(response.status).toBe(200);
    expect(payload.dragonfly.status).toBe('degraded');
    expect(payload.collector.runs).toBe(0);
  });

  it('rejects invalid page query values with a structured 400 response', async () => {
    const response = await app.request('http://localhost/api/ytmusic/saved?page=abc');
    const payload = (await response.json()) as {
      error: string;
      message: string;
      details: Array<{ path: string; message: string }>;
    };

    expect(response.status).toBe(400);
    expect(payload.error).toBe('Invalid request');
    expect(payload.message).toBe('Invalid query parameters');
    expect(payload.details).toContainEqual({
      path: 'page',
      message: 'Page must be a positive integer',
    });
  });

  it('records metrics with the route template instead of the raw path', async () => {
    redisMock.get.mockResolvedValue(null);

    await app.request('http://localhost/api/ytmusic/track-123/analysis');
    const response = await app.request('http://localhost/metrics');
    const metrics = await response.text();

    expect(metrics).toContain('route="/api/ytmusic/:id/analysis"');
    expect(metrics).not.toContain('route="/api/ytmusic/track-123/analysis"');
  });
});
