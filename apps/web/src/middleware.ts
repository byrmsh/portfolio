import type { MiddlewareHandler } from 'astro';

const HTML_CACHE_CONTROL = 'public, max-age=0, must-revalidate';
const ASTRO_ASSET_CACHE_CONTROL = 'public, max-age=31536000, immutable';

export const onRequest: MiddlewareHandler = async ({ url }, next) => {
  const response = await next();

  // Respect route-level caching when a response already defines policy.
  if (response.headers.has('cache-control')) return response;

  const contentType = response.headers.get('content-type') ?? '';
  const isHtml = contentType.includes('text/html');

  if (isHtml) {
    response.headers.set('cache-control', HTML_CACHE_CONTROL);
    return response;
  }

  if (url.pathname.startsWith('/_astro/')) {
    response.headers.set('cache-control', ASTRO_ASSET_CACHE_CONTROL);
    return response;
  }

  return response;
};
