import { z } from 'zod';

const isoDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Expected YYYY-MM-DD');
const isoDatetimeSchema = z
  .string()
  .refine((value: string) => !Number.isNaN(Date.parse(value)), 'Expected ISO datetime');

export const statSourceSchema = z.enum([
  'github',
  'anki',
  'ytmusic',
  'obsidian',
  'writing',
  'cluster',
]);
export const activitySourceSchema = z.enum(['github', 'anki']);
export const serviceStatusSchema = z.enum(['up', 'degraded', 'down']);

export const activityCellSchema = z.object({
  date: isoDateSchema,
  level: z.number().int().min(0).max(4),
  count: z.number().int().min(0),
});

export const activitySeriesSchema = z.object({
  source: activitySourceSchema,
  label: z.string().min(1),
  cells: z.array(activityCellSchema),
  streak: z.number().int().min(0).optional(),
  rolloverHour: z.number().int().min(0).max(23).optional(),
  timezone: z.string().optional(),
  updatedAt: isoDatetimeSchema,
});

export const activityMonitorDataSchema = z.object({
  github: activitySeriesSchema,
  anki: activitySeriesSchema,
});

export const savedLyricNoteSchema = z.object({
  id: z.string().min(1),
  source: z.literal('ytmusic'),
  title: z.string().min(1),
  artist: z.string().min(1),
  noteUrl: z.string().url(),
  albumArtUrl: z.string().url().nullable().optional(),
  savedAt: isoDatetimeSchema,
});

export const ytmusicBackgroundNoteSchema = z.object({
  title: z.string().min(1),
  body: z.string().min(1),
});

export const ytmusicBackgroundSchema = z.object({
  tldr: z.string().min(1),
  notes: z.array(ytmusicBackgroundNoteSchema),
});

export const ytmusicVocabularyItemSchema = z.object({
  id: z.string().min(1),
  term: z.string().min(1),
  exampleDe: z.string().min(1),
  literalEn: z.string().min(1),
  meaningEn: z.string().min(1),
  exampleEn: z.string().min(1),
  memoryHint: z.string().min(1).nullable().optional(),
  cefr: z.string().min(1).nullable().optional(),
  usage: z.array(z.string().min(1)).nullable().optional(),
});

export const ytmusicAnalysisSchema = z.object({
  id: z.string().min(1),
  source: z.literal('ytmusic'),
  title: z.string().min(1),
  artist: z.string().min(1),
  album: z.string().min(1).nullable().optional(),
  albumArtUrl: z.string().url().nullable().optional(),
  trackUrl: z.string().url().nullable().optional(),
  lyricsUrl: z.string().url().nullable().optional(),
  background: ytmusicBackgroundSchema,
  vocabulary: z.array(ytmusicVocabularyItemSchema),
  updatedAt: isoDatetimeSchema,
});

export const writingPostSchema = z.object({
  id: z.string().min(1),
  source: z.literal('writing'),
  title: z.string().min(1),
  description: z.string().min(1),
  href: z.string().min(1),
  tags: z.array(z.string().min(1)),
  publishedAt: isoDatetimeSchema,
});

export const knowledgeGraphSnapshotSchema = z.object({
  source: z.literal('obsidian'),
  nodes: z.number().int().min(0),
  edges: z.number().int().min(0),
  summary: z.string().min(1),
  updatedAt: isoDatetimeSchema,
});

export const serviceHealthSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  detail: z.string().min(1),
  status: serviceStatusSchema,
  pulse: z.boolean(),
  updatedAt: isoDatetimeSchema,
});

export const systemHealthSnapshotSchema = z.object({
  source: z.literal('cluster'),
  namespace: z.string().min(1),
  uptimeRatio30d: z.number().min(0).max(1),
  services: z.array(serviceHealthSchema),
  updatedAt: isoDatetimeSchema,
});

export const dashboardSnapshotSchema = z.object({
  activityMonitor: activityMonitorDataSchema,
  savedLyric: savedLyricNoteSchema.nullable(),
  writing: z.array(writingPostSchema),
  knowledgeGraph: knowledgeGraphSnapshotSchema,
  systemHealth: systemHealthSnapshotSchema,
  updatedAt: isoDatetimeSchema,
});

export const statRedisRecordSchema = z.union([
  activitySeriesSchema,
  savedLyricNoteSchema,
  ytmusicAnalysisSchema,
  writingPostSchema,
  knowledgeGraphSnapshotSchema,
  systemHealthSnapshotSchema,
]);

export type StatSource = z.infer<typeof statSourceSchema>;
export type ActivitySource = z.infer<typeof activitySourceSchema>;
export type ServiceStatus = z.infer<typeof serviceStatusSchema>;
export type ActivityCell = z.infer<typeof activityCellSchema>;
export type ActivitySeries = z.infer<typeof activitySeriesSchema>;
export type ActivityMonitorData = z.infer<typeof activityMonitorDataSchema>;
export type SavedLyricNote = z.infer<typeof savedLyricNoteSchema>;
export type YtMusicBackgroundNote = z.infer<typeof ytmusicBackgroundNoteSchema>;
export type YtMusicBackground = z.infer<typeof ytmusicBackgroundSchema>;
export type YtMusicVocabularyItem = z.infer<typeof ytmusicVocabularyItemSchema>;
export type YtMusicAnalysis = z.infer<typeof ytmusicAnalysisSchema>;
export type WritingPost = z.infer<typeof writingPostSchema>;
export type KnowledgeGraphSnapshot = z.infer<typeof knowledgeGraphSnapshotSchema>;
export type ServiceHealth = z.infer<typeof serviceHealthSchema>;
export type SystemHealthSnapshot = z.infer<typeof systemHealthSnapshotSchema>;
export type DashboardSnapshot = z.infer<typeof dashboardSnapshotSchema>;
export type StatRedisRecord = z.infer<typeof statRedisRecordSchema>;

export type ApiEnvelope<T> = {
  data: T;
  meta: Record<string, unknown>;
};

export const redisKeys = {
  stat: (source: StatSource, id: string | number) => `stat:${source}:${id}`,
  statField: (source: StatSource, id: string | number, field: string) =>
    `stat:${source}:${id}:${field}`,
  index: {
    writingRecent: 'index:writing:recent',
    lyricsRecent: 'index:ytmusic:saved',
    lyricsAnalysisPending: 'index:ytmusic:analysis:pending',
  },
} as const;

export function parseDashboardSnapshot(value: unknown): DashboardSnapshot {
  return dashboardSnapshotSchema.parse(value);
}

export function parseStatRedisRecord(value: unknown): StatRedisRecord {
  return statRedisRecordSchema.parse(value);
}

export function parseApiEnvelope<TSchema extends z.ZodTypeAny>(
  value: unknown,
  dataSchema: TSchema,
): ApiEnvelope<z.infer<TSchema>> {
  return z
    .object({
      data: dataSchema,
      meta: z.record(z.unknown()),
    })
    .parse(value) as ApiEnvelope<z.infer<TSchema>>;
}
