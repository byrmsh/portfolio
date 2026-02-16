import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { SITE } from '../config/site';
import { DEFAULT_LOCALE, getTranslator, localizedPath } from '../i18n';

export const prerender = false;

export async function GET(context: { site?: URL }) {
  const locale = DEFAULT_LOCALE;
  const t = getTranslator(locale);

  const posts = (await getCollection('blog'))
    .filter((p) => !p.data.draft)
    .sort((a, b) => b.data.pubDate.getTime() - a.data.pubDate.getTime());

  const site = context.site ?? new URL(`https://${SITE.domain}`);

  return rss({
    title: `${SITE.name} | ${t('meta.blog')}`,
    description: t('blog.description'),
    site,
    customData: `<language>${locale}</language>`,
    items: posts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.pubDate,
      link: localizedPath(locale, `/blog/${post.slug}`),
      categories: post.data.tags,
    })),
  });
}
