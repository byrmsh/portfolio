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
    http_error: 'HTTP {status}',
    loading: 'Loading',
    error: 'Error',
    close_dialog: 'Close dialog',
    back_to_top: 'Back to top',
    date_formats: {
      saved_at: 'Saved {date}',
      published_at: 'Published {date}',
      captured_at: 'Captured {date}',
      updated_at: 'Updated {date}',
    },
  },
  errors: {
    not_found: 'Not found',
    invalid_response: 'Invalid response',
    failed_to_load: 'Failed to load',
    network_error: 'Network error',
    unauthorized: 'Unauthorized',
  },
  meta: {
    systems_console: 'Systems Console',
    blog: 'Blog',
    contact: 'Contact',
    lyrics: 'Playlist',
    lyric_note: 'Playlist Breakdown',
    projects: 'Projects',
  },
  blog: {
    eyebrow: 'Blog',
    title: 'Writing Log',
    description: 'Project logs, notes, and system documentation.',
    back_to_all: '← ALL POSTS',
    published: 'Published {date}',
    updated: 'Updated {date}',
  },
  nav: {
    home: 'Home',
    blog: 'Blog',
    lyrics: 'Playlist',
    projects: 'Projects',
    contact: 'Contact',
    open_menu: 'Open menu',
    language: 'Language',
  },
  contact: {
    eyebrow: 'Contact',
    title: 'Say Hello',
    description:
      'Open to new opportunities and technical discussions! PGP key available for encryption.',
    email_label: 'Email',
    gpg_label: 'PGP Public Key',
  },
  hero: {
    pronunciation: '/bajˈɾam ʃaˈhin/',
    pronunciation_simple: 'bye-RAHM sha-HEEN',
    subtitle: 'Full-Stack Developer & DevOps Practitioner',
  },
  activity: {
    title: 'Activity Monitor',
    last7Days: 'Last 7 days',
    range_label: '{start} to {end}',
    github_label: 'GitHub',
    anki_label: 'Anki',
    github_aria: 'GitHub activity, last 7 days',
    anki_aria: 'Anki activity, last 7 days',
    github_day_aria: 'GitHub day {day}',
    anki_day_aria: 'Anki day {day}',
    streak_days: 'Streak: {count}',
    tooltip_with_date: '{label}: {date} ({count} {unit})',
    tooltip_without_date: '{label}: ({count} {unit})',
  },
  saved_lyrics: {
    title: 'Playlist',
    no_tracks: 'No saved tracks yet',
    synced_at: 'Synced: {value}',
    read_lyric_note: 'READ BREAKDOWN',
  },
  writing: {
    title: 'Writing',
    all_posts: 'All Posts',
  },
  knowledge_graph: {
    title: 'Knowledge Graph',
    source: 'OBSIDIAN',
    stats: '{nodes} nodes · {links} links',
    fullscreen: 'Fullscreen',
    exit_fullscreen: 'Exit fullscreen',
    no_script: 'Enable JavaScript to load the interactive graph.',
  },
  projects_widget: {
    title: 'Projects',
    view_all: 'All Projects',
    empty: 'No projects published yet.',
  },
  health: {
    title: 'Live Infrastructure',
    uptime_label: 'UPTIME',
    availability_label: 'AVAILABILITY',
    latency_label: 'LATENCY',
    recency_label: 'RECENCY',
    runs: {
      one: '{count} run',
      other: '{count} runs',
    },
    checked_at: 'Checked: {value}',
  },
  git_commits: {
    title: 'Latest Updates',
    post_updates_title: 'Post Updates',
    total_changes: 'Total changes: {value}',
    author: 'AUTHOR',
    date: 'DATE',
    hash: 'HASH',
    open_commit: 'Open commit {hash}',
    breaking: 'BREAKING',
    type_feat: 'FEATURE',
    type_fix: 'FIX',
    type_docs: 'DOCUMENTATION',
    type_chore: 'MAINTENANCE',
    type_refactor: 'REFACTOR',
    type_test: 'TEST',
    type_perf: 'PERFORMANCE',
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
    saved_at: 'Saved {date}',
    no_tracks: 'No tracks processed yet.',
    all: 'All',
    total: '{count} total',
    page: 'Page {page} / {totalPages}',
    per_page: '{count}/page',
    could_not_load_page: 'Could not load page: {error}',
    prev: 'PREV',
    next: 'NEXT',
    back_to_all: '← ALL TRACKS',
    loading: 'Loading…',
    could_not_load_note: 'Could not load playlist breakdown',
    note_label: 'Playlist Breakdown',
    open_track: 'OPEN TRACK',
    read_lyrics: 'READ LYRICS',
    updated_at: 'Updated {date}',
    background: 'Background',
    vocabulary: 'Vocabulary',
    flashcards: 'Practice Deck',
    flashcards_flip_hint: 'Tap card to flip',
    flashcards_tap_hint: 'Tap',
    flashcards_rate_hint: 'Swipe card to rate',
    flashcards_known_hint: 'Easy',
    flashcards_review_hint: 'Hard',
    flashcards_round: 'Round {round}',
    flashcards_completed: 'Deck complete',
    flashcards_completed_sub: 'You cleared this track. Reset progress any time to practice again.',
    flashcards_remaining: '{count} cards left',
    flashcards_reset: 'Reset progress',
    flashcards_no_script: 'Enable JavaScript to use the flashcard deck.',
    literal: 'Literal:',
    meaning: 'Meaning:',
    not_found: 'Not found',
    invalid_response: 'Invalid response',
    failed_to_load: 'Failed to load',
  },
  projects: {
    eyebrow: 'Projects',
    title: 'Project Archive',
    description: 'Selected builds, archived experiments, and works in progress.',
    back_to_all: '← ALL PROJECTS',
    gallery_prev: 'Previous image',
    gallery_next: 'Next image',
    gallery_maximize: 'Maximize',
    gallery_image_alt: '{title} image {index}',
    gallery_no_script:
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
