import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { SITE } from '../../config/site';
import { DEFAULT_LOCALE, getTranslator, isSupportedLocale, localizedPath } from '../../i18n';

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

  return rss({
    title: `${SITE.name} | ${t('nav.blog')}`,
    description: t('blog.indexDescription'),
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
};
