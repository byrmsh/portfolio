import {
  DEFAULT_LOCALE,
  SUPPORTED_LOCALES,
  translations,
  type SupportedLocale,
} from './translations';

export { DEFAULT_LOCALE, SUPPORTED_LOCALES, type SupportedLocale };

type Primitive = string | number;

export function normalizeLocale(locale: string | undefined | null): SupportedLocale {
  if (locale && SUPPORTED_LOCALES.includes(locale as SupportedLocale)) {
    return locale as SupportedLocale;
  }
  return DEFAULT_LOCALE;
}

export function isSupportedLocale(locale: string | undefined | null): locale is SupportedLocale {
  return !!locale && SUPPORTED_LOCALES.includes(locale as SupportedLocale);
}

function interpolate(template: string, vars?: Record<string, Primitive>): string {
  if (!vars) return template;
  return template.replaceAll(/\{(\w+)\}/g, (_, key: string) => String(vars[key] ?? `{${key}}`));
}

function getByPath(dict: unknown, path: string): string {
  const value = path.split('.').reduce<unknown>((acc, segment) => {
    if (acc && typeof acc === 'object' && segment in acc) {
      return (acc as Record<string, unknown>)[segment];
    }
    return undefined;
  }, dict);

  if (typeof value !== 'string') {
    throw new Error(`Missing translation key: ${path}`);
  }

  return value;
}

export function getTranslator(locale: SupportedLocale) {
  const dict = translations[locale];
  return (path: string, vars?: Record<string, Primitive>) =>
    interpolate(getByPath(dict, path), vars);
}

export function getLocaleFromUrl(url: URL): SupportedLocale {
  const first = url.pathname.split('/').filter(Boolean)[0];
  return normalizeLocale(first);
}

export function localizedPath(locale: SupportedLocale, path = '/', baseSearch?: string): string {
  const clean = path.startsWith('/') ? path : `/${path}`;
  const parts = clean.split('/').filter(Boolean);
  const stripped = parts.length && isSupportedLocale(parts[0]) ? `/${parts.slice(1).join('/')}` : clean;
  const withLocale =
    locale === DEFAULT_LOCALE
      ? stripped
      : `/${locale}${stripped === '/' ? '' : stripped}`;
  const params = new URLSearchParams(baseSearch ?? '');
  // Query-param locale is deprecated; ensure we don't carry it forward.
  params.delete('lang');
  const query = params.toString();
  return `${withLocale}${query ? `?${query}` : ''}`;
}
