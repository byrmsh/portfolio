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
});
