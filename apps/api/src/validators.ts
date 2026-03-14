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
  page: z.preprocess(
    (value) => {
      if (Array.isArray(value)) return value[0] ?? '1';
      return value ?? '1';
    },
    z
      .string()
      .regex(/^\d+$/, 'Page must be a positive integer')
      .transform((value) => Number.parseInt(value, 10))
      .refine((value) => value >= 1, 'Page must be at least 1'),
  ),
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
export function validatePathParams<TSchema extends z.ZodTypeAny>(
  schema: TSchema,
  params: Record<string, string | string[] | undefined>,
): z.infer<TSchema> {
  return validateRequestData(schema, params, 'Invalid path parameters');
}

export function validateQueryParams<TSchema extends z.ZodTypeAny>(
  schema: TSchema,
  params: Record<string, string | string[] | undefined>,
): z.infer<TSchema> {
  return validateRequestData(schema, params, 'Invalid query parameters');
}

function validateRequestData<TSchema extends z.ZodTypeAny>(
  schema: TSchema,
  params: Record<string, string | string[] | undefined>,
  message: string,
): z.infer<TSchema> {
  const result = schema.safeParse(params);
  if (!result.success) {
    const errors = result.error.errors.map((err) => ({
      path: err.path.join('.'),
      message: err.message,
    }));
    throw new ValidationError(message, errors);
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
