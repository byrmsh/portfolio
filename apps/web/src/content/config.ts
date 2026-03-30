import { defineCollection, z } from 'astro:content';

const blog = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    heroImage: z.string().optional(),
    draft: z.boolean().default(false),
    tags: z.array(z.string()).default([]),
  }),
});

const projects = defineCollection({
  type: 'content',
  schema: ({ image }) =>
    z.object({
      title: z.string(),
      description: z.string(),
      summary: z.string(),
      year: z.number().int().min(1990).max(2100),
      stack: z.array(z.string()).min(1),
      heroImage: image(),
      galleryImages: z.array(image()).default([]),
      featured: z.boolean().default(false),
      order: z.number().int().min(1).default(100),
      draft: z.boolean().default(false),
    }),
});

export const collections = { blog, projects };
