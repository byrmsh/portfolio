import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { SITE } from '../../config/site';
import {
  DEFAULT_LOCALE,
  NOINDEX_LOCALES,
  getTranslator,
  isSupportedLocale,
  localizedPath,
} from '../../i18n';

export const prerender = false;

export async function GET(context: { site?: URL; params: { lang?: string } }) {
  const { lang } = context.params;
  if (!lang || !isSupportedLocale(lang)) return new Response(null, { status: 404 });
  if (lang === DEFAULT_LOCALE) {
    return new Response(null, {
      status: 302,
      headers: { Location: '/rss.xml' },
    });
  }

  const locale = lang;
  const t = getTranslator(locale);

  const posts = (await getCollection('blog'))
    .filter((p) => !p.data.draft)
    .sort((a, b) => b.data.pubDate.getTime() - a.data.pubDate.getTime());

  const site = context.site ?? new URL(`https://${SITE.domain}`);

  const response = await rss({
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
  if (NOINDEX_LOCALES.includes(locale)) response.headers.set('X-Robots-Tag', 'noindex');
  return response;
}
