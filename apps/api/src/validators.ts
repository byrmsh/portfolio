import { z } from 'zod';
import { activitySourceSchema } from '@portfolio/schema/dashboard';

/**
 * Validator for the activity source path parameter.
 */
export const activitySourceParamSchema = z.object({
  source: activitySourceSchema,
});

/**
 * Validator for the page query parameter.
 * Handles string, array, or undefined input.
 */
export const pageQuerySchema = z.object({
  page: z.union([z.string(), z.array(z.string()), z.undefined()]).transform((val) => {
    let strVal: string;
    if (Array.isArray(val)) {
      strVal = val[0] || '1';
    } else if (typeof val === 'string') {
      strVal = val;
    } else {
      strVal = '1';
    }
    const parsed = Number.parseInt(strVal, 10);
    return Number.isNaN(parsed) ? 1 : parsed;
  }),
});

/**
 * Validator for the track ID path parameter.
 */
export const trackIdParamSchema = z.object({
  id: z.string().min(1, 'Track ID must not be empty'),
});

/**
 * Utility to validate request path parameters.
 * Returns parsed data or throws a validation error with details.
 */
export function validatePathParams<T>(
  schema: z.ZodSchema<T>,
  params: Record<string, string | string[] | undefined>,
): T {
  const result = schema.safeParse(params);
  if (!result.success) {
    const errors = result.error.errors.map((err) => ({
      path: err.path.join('.'),
      message: err.message,
    }));
    throw new ValidationError('Invalid path parameters', errors);
  }
  return result.data;
}

/**
 * Custom error class for validation errors.
 */
export class ValidationError extends Error {
  constructor(
    public message: string,
    public details: Array<{ path: string; message: string }>,
  ) {
    super(message);
    this.name = 'ValidationError';
  }
}
