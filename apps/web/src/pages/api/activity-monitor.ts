import type { APIRoute } from 'astro';

const DEFAULT_API_ORIGIN = 'http://localhost:3000';

export const GET: APIRoute = async () => {
  const apiOrigin =
    process.env.API_ORIGIN ??
    import.meta.env.API_ORIGIN ??
    import.meta.env.PUBLIC_API_ORIGIN ??
    DEFAULT_API_ORIGIN;
  const upstreamUrl = `${String(apiOrigin).replace(/\/$/, '')}/api/activity-monitor`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2500);
  try {
    const upstream = await fetch(upstreamUrl, {
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal,
      headers: { accept: 'application/json' },
    });
    const body = await upstream.text();
    return new Response(body, {
      status: upstream.status,
      headers: {
        'content-type': upstream.headers.get('content-type') ?? 'application/json; charset=utf-8',
        'cache-control': 'no-store',
      },
    });
  } catch {
    return new Response(JSON.stringify({ data: null, error: 'upstream_unreachable' }), {
      status: 502,
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'no-store',
      },
    });
  } finally {
    clearTimeout(timeout);
  }
};
