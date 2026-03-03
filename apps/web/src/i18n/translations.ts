export const SUPPORTED_LOCALES = ['eng', 'dev'] as const;

export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: SupportedLocale = 'eng';

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

// Helper to generate test translations that display keys
function generateKeyDisplayTranslations(obj: TranslationDict, prefix = ''): TranslationDict {
  const result: TranslationDict = {};
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      result[key] = fullKey;
    } else {
      result[key] = generateKeyDisplayTranslations(value, fullKey);
    }
  }
  return result;
}

const enTranslations = {
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
    blog: 'Blog',
    contact: 'Contact',
    lyrics: 'Playlist',
    lyricNote: 'Playlist Breakdown',
    projects: 'Projects',
  },
  blog: {
    eyebrow: 'Blog',
    title: 'Writing Log',
    description: 'Project logs, notes, and system documentation.',
    backToAll: '← ALL POSTS',
    published: 'Published {date}',
    updated: 'Updated {date}',
  },
  nav: {
    home: 'Home',
    blog: 'Blog',
    lyrics: 'Playlist',
    projects: 'Projects',
    contact: 'Contact',
    openMenu: 'Open menu',
    language: 'Language',
  },
  contact: {
    eyebrow: 'Contact',
    title: 'Say Hello',
    description:
      'Open to new opportunities and technical discussions! PGP key available for encryption.',
    emailLabel: 'Email',
    gpgLabel: 'PGP Public Key',
  },
  hero: {
    pronunciation: '/bajˈɾam ʃaˈhin/',
    pronunciationSimple: 'bye-RAHM sha-HEEN',
    subtitle: 'Full-Stack Developer & DevOps Practitioner',
  },
  activity: {
    title: 'Activity Monitor',
    last7Days: 'Last 7 days',
    rangeLabel: '{start} to {end}',
    githubLabel: 'GitHub',
    ankiLabel: 'Anki',
    githubAria: 'GitHub activity, last 7 days',
    ankiAria: 'Anki activity, last 7 days',
    githubDayAria: 'GitHub day {day}',
    ankiDayAria: 'Anki day {day}',
    streak: 'Streak',
    tooltipWithDate: '{label}: {date} ({count} {unit})',
    tooltipWithoutDate: '{label}: ({count} {unit})',
  },
  savedLyrics: {
    title: 'Playlist',
    noTracks: 'No saved tracks yet',
    readLyricNote: 'READ BREAKDOWN',
  },
  writing: {
    title: 'Writing',
    allPosts: 'All Posts',
  },
  knowledgeGraph: {
    title: 'Knowledge Graph',
    source: 'OBSIDIAN',
    stats: '{nodes} nodes · {links} links',
    fullscreen: 'Fullscreen',
    exitFullscreen: 'Exit fullscreen',
    noScript: 'Enable JavaScript to load the interactive graph.',
  },
  projectsWidget: {
    title: 'Projects',
    viewAll: 'All Projects',
    empty: 'No projects published yet.',
  },
  health: {
    title: 'Live Infrastructure',
    uptimeLabel: 'UPTIME',
    availabilityLabel: 'AVAILABILITY',
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
    typePerf: 'PERFORMANCE',
    empty: 'No commit history available.',
  },
  footer: {
    copyright: '© {year} {name}',
    source: 'Source',
    rss: 'RSS',
  },
  lyrics: {
    eyebrow: 'Playlist',
    title: 'Processed Lyrics',
    description:
      'I like dissecting German song lyrics for language learning; here is my playlist processed & served for fun.',
    latest: 'Latest',
    savedAt: 'Saved {date}',
    noTracks: 'No tracks processed yet.',
    all: 'All',
    total: '{count} total',
    page: 'Page {page} / {totalPages}',
    perPage: '{count}/page',
    couldNotLoadPage: 'Could not load page: {error}',
    prev: 'PREV',
    next: 'NEXT',
    backToAll: '← ALL TRACKS',
    loading: 'Loading…',
    couldNotLoadNote: 'Could not load playlist breakdown',
    noteLabel: 'Playlist Breakdown',
    openTrack: 'OPEN TRACK',
    readLyrics: 'READ LYRICS',
    updatedAt: 'Updated {date}',
    background: 'Background',
    vocabulary: 'Vocabulary',
    flashcards: 'Practice Deck',
    flashcardsFlipHint: 'Tap card to flip',
    flashcardsTapHint: 'Tap',
    flashcardsRateHint: 'Swipe card to rate',
    flashcardsKnownHint: 'Easy',
    flashcardsReviewHint: 'Hard',
    flashcardsRound: 'Round {round}',
    flashcardsCompleted: 'Deck complete',
    flashcardsCompletedSub: 'You cleared this track. Reset progress any time to practice again.',
    flashcardsRemaining: '{count} cards left',
    flashcardsReset: 'Reset progress',
    flashcardsNoScript: 'Enable JavaScript to use the flashcard deck.',
    literal: 'Literal:',
    meaning: 'Meaning:',
    notFound: 'Not found',
    invalidResponse: 'Invalid response',
    failedToLoad: 'Failed to load',
  },
  projects: {
    eyebrow: 'Projects',
    title: 'Project Archive',
    description: 'Selected builds, archived experiments, and works in progress.',
    backToAll: '← ALL PROJECTS',
    galleryPrev: 'Previous image',
    galleryNext: 'Next image',
    galleryMaximize: 'Maximize',
    galleryImageAlt: '{title} image {index}',
    galleryNoScript:
      'JavaScript is disabled, so all project images are listed in place of the gallery.',
  },
};

export const translations: Record<SupportedLocale, TranslationDict> = {
  eng: enTranslations,
  dev: generateKeyDisplayTranslations(enTranslations),
};

export type TranslationKey = DeepKeys<typeof enTranslations>;

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

export function plural(count: number, singular: string, plural: string): string {
  return count === 1 ? singular : plural;
}
