import { z } from "zod";

// Mirrors the current Upwork payload shape defined by apps/upworker/typex.py
// and selected in apps/upworker/job-search.gql.
const nullableString = z.string().nullable();
const nullableBool = z.boolean().nullable();

const nullableNumberLike = z.preprocess((value) => {
  if (value === null || value === undefined) return value;
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.length === 0) return null;
    const n = Number(trimmed);
    return Number.isFinite(n) ? n : value;
  }
  return value;
}, z.number().nullable());

export const upworkFixedPriceAmountSchema = z.object({
  isoCurrencyCode: nullableString,
  amount: z.string(),
});

export const upworkClientInfoSchema = z.object({
  paymentVerificationStatus: nullableString,
  country: nullableString,
  totalReviews: z.number().int(),
  totalFeedback: z.number(),
  hasFinancialPrivacy: z.boolean(),
  totalSpent: upworkFixedPriceAmountSchema.nullable(),
});

export const upworkFreelancerClientRelationSchema = z.object({
  lastContractRid: nullableString,
  companyName: nullableString,
  lastContractTitle: nullableString,
});

export const upworkHistoryDataSchema = z.object({
  client: upworkClientInfoSchema,
  freelancerClientRelation: upworkFreelancerClientRelationSchema,
});

export const upworkEngagementDurationSchema = z.object({
  rid: z.number().int(),
  label: z.string(),
  weeks: z.number().int(),
  ctime: z.string(),
  mtime: z.string(),
});

export const upworkJobDetailsSchema = z.object({
  id: z.string(),
  ciphertext: z.string(),
  jobType: z.enum(["FIXED", "HOURLY"]),
  // Upwork sometimes returns numeric fields as strings.
  weeklyRetainerBudget: nullableNumberLike,
  hourlyBudgetMax: nullableNumberLike,
  hourlyBudgetMin: nullableNumberLike,
  hourlyEngagementType: nullableString,
  contractorTier: z.string(),
  sourcingTimestamp: nullableString,
  createTime: z.string(),
  publishTime: z.string(),
  enterpriseJob: z.boolean(),
  personsToHire: z.number().int(),
  premium: z.boolean(),
  totalApplicants: z.number().int().nullable(),
  hourlyEngagementDuration: upworkEngagementDurationSchema.nullable(),
  fixedPriceAmount: upworkFixedPriceAmountSchema.nullable(),
  fixedPriceEngagementDuration: upworkEngagementDurationSchema.nullable(),
});

export const upworkJobTileSchema = z.object({
  job: upworkJobDetailsSchema,
});

export const upworkOntologySkillSchema = z.object({
  uid: z.string(),
  parentSkillUid: nullableString,
  prefLabel: z.string(),
  prettyName: z.string(),
  freeText: nullableString,
  highlighted: z.boolean(),
});

export const upworkFacetValueSchema = z.object({
  key: z.string(),
  value: z.number().int(),
});

export const upworkFacetsSchema = z.object({
  jobType: z.array(upworkFacetValueSchema),
  workload: z.array(upworkFacetValueSchema),
  clientHires: z.array(upworkFacetValueSchema),
  durationV3: z.array(upworkFacetValueSchema),
  amount: z.array(upworkFacetValueSchema),
  contractorTier: z.array(upworkFacetValueSchema),
  contractToHire: z.array(upworkFacetValueSchema),
  paymentVerified: z.array(upworkFacetValueSchema),
  proposals: z.array(upworkFacetValueSchema),
  previousClients: z.array(upworkFacetValueSchema),
});

export const upworkPagingSchema = z.object({
  total: z.number().int(),
  offset: z.number().int(),
  count: z.number().int(),
});

export const upworkJobResultSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string(),
  relevanceEncoded: z.string(),
  ontologySkills: z.array(upworkOntologySkillSchema),
  isSTSVectorSearchResult: z.boolean().or(nullableBool),
  // Not selected in job-search.gql (historical field).
  connectPrice: z.number().int().nullable().optional(),
  applied: z.boolean().nullable(),
  upworkHistoryData: upworkHistoryDataSchema,
  jobTile: upworkJobTileSchema,
});

export const upworkJobSearchResponseSchema = z.object({
  data: z.object({
    search: z.object({
      universalSearchNuxt: z.object({
        userJobSearchV1: z.object({
          paging: upworkPagingSchema,
          facets: upworkFacetsSchema,
          results: z.array(upworkJobResultSchema),
        }),
      }),
    }),
  }),
});

export type UpworkJobResult = z.infer<typeof upworkJobResultSchema>;
export type UpworkJobSearchResponse = z.infer<typeof upworkJobSearchResponseSchema>;

export function parseUpworkJobSearchResponse(value: unknown): UpworkJobSearchResponse {
  return upworkJobSearchResponseSchema.parse(value);
}
