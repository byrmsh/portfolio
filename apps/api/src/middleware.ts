import { Context, Next } from 'hono';
import { Counter, Histogram, register, collectDefaultMetrics } from 'prom-client';

// Initialize default metrics (cpu, memory, gc)
collectDefaultMetrics();

// Define Prometheus metrics
export const httpRequestDuration = new Histogram({
  name: 'http_request_duration_seconds',
  help: 'Duration of HTTP requests in seconds',
  labelNames: ['method', 'route', 'status'],
  buckets: [0.001, 0.01, 0.1, 0.5, 1, 2, 5],
});

export const httpRequestTotal = new Counter({
  name: 'http_requests_total',
  help: 'Total count of HTTP requests',
  labelNames: ['method', 'route', 'status'],
});

export const httpRequestErrors = new Counter({
  name: 'http_request_errors_total',
  help: 'Total count of HTTP request errors',
  labelNames: ['method', 'route', 'error_type'],
});

export const redisConnectionErrors = new Counter({
  name: 'redis_connection_errors_total',
  help: 'Total count of Redis connection errors',
  labelNames: ['operation'],
});

/**
 * Middleware to measure HTTP request duration and count.
 * Should be applied early in the middleware chain.
 */
export async function metricsMiddleware(c: Context, next: Next) {
  const startTime = Date.now();
  const route = c.req.path;
  const method = c.req.method;

  try {
    await next();
    const duration = (Date.now() - startTime) / 1000;
    const status = c.res.status;

    httpRequestDuration.labels(method, route, String(status)).observe(duration);
    httpRequestTotal.labels(method, route, String(status)).inc();
  } catch (error) {
    const duration = (Date.now() - startTime) / 1000;
    const errorType = error instanceof Error ? error.constructor.name : 'Unknown';

    httpRequestDuration.labels(method, route, '500').observe(duration);
    httpRequestTotal.labels(method, route, '500').inc();
    httpRequestErrors.labels(method, route, errorType).inc();

    throw error;
  }
}

/**
 * Middleware to catch errors, log them with context, and return proper error responses.
 */
export async function errorHandlingMiddleware(c: Context, next: Next) {
  try {
    await next();
  } catch (error) {
    const method = c.req.method;
    const path = c.req.path;
    const requestTime = new Date().toISOString();

    const errorInfo = {
      timestamp: requestTime,
      method,
      path,
      query: c.req.query(),
      error: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
    };

    // Log error with context
    console.error('[API Error]', JSON.stringify(errorInfo));

    // Return structured error response
    return c.json(
      {
        error: 'Internal Server Error',
        message: error instanceof Error ? error.message : 'An unexpected error occurred',
        meta: {
          ts: requestTime,
          path,
          method,
        },
      },
      500,
    );
  }
}

/**
 * Get Prometheus metrics in text format.
 */
export async function getMetrics(): Promise<string> {
  return register.metrics();
}
