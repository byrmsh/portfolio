export const SUPPORTED_LOCALES = ['en'] as const;

export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: SupportedLocale = 'en';

type TranslationDict = {
  [key: string]: string | TranslationDict;
};

// Type-safe translation keys
type DeepKeys<T> = T extends object
  ? {
      [K in keyof T]: K extends string
        ? T[K] extends object
          ? `${K}.${DeepKeys<T[K]>}`
          : K
        : never;
    }[keyof T]
  : never;

export type TranslationKey = DeepKeys<typeof translations.en>;

// Translation helper with interpolation support
export function t(
  key: TranslationKey,
  params?: Record<string, string | number>,
  locale: SupportedLocale = DEFAULT_LOCALE,
): string {
  const keys = key.split('.');
  let value: TranslationDict | string = translations[locale];

  for (const k of keys) {
    if (typeof value === 'string') return key;
    value = value?.[k];
    if (!value) return key;
  }

  if (typeof value !== 'string') return key;

  if (!params) return value;

  return value.replace(/\{(\w+)\}/g, (_, k) => String(params[k] ?? ''));
}

// Pluralization helper
export function plural(count: number, singular: string, plural: string): string {
  return count === 1 ? singular : plural;
}

export const translations: Record<SupportedLocale, TranslationDict> = {
  en: {
    common: {
      httpError: 'HTTP {status}',
      loading: 'Loading',
      error: 'Error',
      closeDialog: 'Close dialog',
      backToTop: 'Back to top',
      dateFormats: {
        savedAt: 'Saved {date}',
        publishedAt: 'Published {date}',
        capturedAt: 'Captured {date}',
        updatedAt: 'Updated {date}',
      },
    },
    errors: {
      notFound: 'Not found',
      invalidResponse: 'Invalid response',
      failedToLoad: 'Failed to load',
      networkError: 'Network error',
      unauthorized: 'Unauthorized',
    },
    meta: {
      systemsConsole: 'Systems Console',
      lyrics: 'Lyrics',
      lyricNote: 'Lyric Note',
      jobs: 'Jobs',
    },
    blog: {
      indexDescription: 'Project logs, notes, and system documentation.',
      updatedInline: ' · updated {date}',
    },
    nav: {
      home: 'Home',
      blog: 'Blog',
      lyrics: 'Lyrics',
      jobs: 'Jobs',
      contact: 'Contact',
      openMenu: 'Open menu',
      language: 'Language',
    },
    contact: {
      description:
        'Open to new opportunities and technical discussions! GPG key available for encryption.',
      emailLabel: 'Email',
      gpgLabel: 'GPG Public Key',
    },
    hero: {
      subtitle: 'Full-Stack Developer & DevOps Practitioner.',
      description: 'Building software and writing about what I learn along the way.',
    },
    activity: {
      title: 'Activity Monitor',
      last7Days: 'Last 7 days',
      to: 'to',
      githubLabel: 'GitHub',
      ankiLabel: 'Anki',
      githubAria: 'GitHub activity, last 7 days',
      ankiAria: 'Anki activity, last 7 days',
      githubDayAria: 'GitHub day {day}',
      ankiDayAria: 'Anki day {day}',
      streak: 'Streak',
      tooltipWithDate: '{label}: {date} ({count})',
      tooltipWithoutDate: '{label}: ({count})',
    },
    savedLyrics: {
      title: 'Saved Lyrics',
      noTracks: 'No saved tracks yet',
      readLyricNote: 'READ NOTE',
    },
    writing: {
      title: 'Writing',
      allPosts: 'All Posts',
    },
    knowledgeGraph: {
      title: 'Knowledge Graph',
      source: 'OBSIDIAN',
      nodes: '{count} Nodes',
      description: 'Interlinked notes on DevOps, Philosophy, and Music.',
    },
    jobScout: {
      title: 'Job Scout',
      source: 'Upwork',
      emptyLead: 'No captured job leads yet.',
      emptyTag: 'Awaiting data stream',
      viewAll: 'View all captured leads',
    },
    health: {
      title: 'Live Infrastructure',
      latencyLabel: 'LATENCY',
      recencyLabel: 'RECENCY',
      notAvailable: 'n/a',
      runs: {
        one: '{count} run',
        other: '{count} runs',
      },
      checkedPrefix: 'CHECKED',
    },
    gitCommits: {
      title: 'Latest Updates',
      postUpdatesTitle: 'Post Updates',
      totalChanges: 'TOTAL CHANGES: {value}',
      author: 'AUTHOR',
      date: 'DATE',
      hash: 'HASH',
      openCommit: 'Open commit {hash}',
      breaking: 'BREAKING',
      typeFeat: 'FEATURE',
      typeFix: 'FIX',
      typeDocs: 'DOCUMENTATION',
      typeChore: 'MAINTENANCE',
      typeRefactor: 'REFACTOR',
      typeTest: 'TEST',
      empty: 'No commit history available.',
    },
    footer: {
      copyright: '© {year} {name}',
      source: 'Source',
      rss: 'RSS',
    },
    lyrics: {
      eyebrow: 'Lyrics',
      title: 'Lyric Notes',
      description:
        'Background analysis and vocabulary notes. Full lyrics are hosted on external sites.',
      latest: 'Latest',
      savedAt: 'Saved {date}',
      noTracks: 'No tracks processed yet.',
      all: 'All ({count})',
      page: 'Page {page} / {totalPages}',
      perPage: '{count}/page',
      couldNotLoadPage: 'Could not load page: {error}',
      prev: 'PREV',
      next: 'NEXT',
      backToAll: '← ALL NOTES',
      loading: 'Loading…',
      couldNotLoadNote: 'Could not load note',
      noteLabel: 'Lyric Note',
      openTrack: 'OPEN TRACK',
      readLyrics: 'READ LYRICS',
      updatedAt: 'Updated {date}',
      background: 'Background',
      vocabulary: 'Vocabulary',
      literal: 'Literal:',
      meaning: 'Meaning:',
      notFound: 'Not found',
      invalidResponse: 'Invalid response',
      failedToLoad: 'Failed to load',
    },
    jobs: {
      eyebrow: 'Jobs',
      title: 'Captured Leads',
      description: 'Recent Upwork job leads captured from the ingestion worker.',
      empty: 'No jobs captured yet.',
      newest: 'NEWEST',
      next: 'NEXT',
      backToAll: '← ALL JOBS',
      openUpwork: 'OPEN UPWORK',
      published: 'Published {date}',
      captured: 'Captured {date}',
      notFound: 'Job not found',
      facts: 'Facts',
      factType: 'TYPE',
      factTier: 'TIER',
      factCountry: 'COUNTRY',
      factPayment: 'PAYMENT',
      factSpent: 'SPENT',
      factBudget: 'BUDGET',
    },
  },
};
