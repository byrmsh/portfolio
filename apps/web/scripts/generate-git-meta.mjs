import { execSync } from 'node:child_process';
import { readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const RECENT_LIMIT = 3;
const OUTPUT_PATH = 'apps/web/dist/git-meta.json';
const BLOG_CONTENT_DIR = 'apps/web/src/content/blog';
const PROJECTS_CONTENT_DIR = 'apps/web/src/content/projects';
const LOG_FORMAT = '%H%x1f%h%x1f%aN%x1f%aI%x1f%s';

function normalizeGitHubRepoUrl(remote) {
  const trimmed = String(remote ?? '')
    .trim()
    .replace(/\.git$/, '');
  if (!trimmed) return null;

  if (trimmed.startsWith('https://github.com/')) return trimmed;

  if (trimmed.startsWith('git@github.com:')) {
    const path = trimmed.slice('git@github.com:'.length);
    return path ? `https://github.com/${path}` : null;
  }

  if (trimmed.startsWith('ssh://git@github.com/')) {
    const path = trimmed.slice('ssh://git@github.com/'.length);
    return path ? `https://github.com/${path}` : null;
  }

  return null;
}

function runGit(cmd) {
  return execSync(cmd, { encoding: 'utf8' }).trim();
}

function getRecentCommits(paths = []) {
  const pathArgs = paths.length ? ` -- ${paths.map((p) => JSON.stringify(p)).join(' ')}` : '';
  const rawLog = runGit(
    `git log -n ${RECENT_LIMIT} --date=iso-strict --pretty=format:${LOG_FORMAT}${pathArgs}`,
  );
  return rawLog
    ? rawLog
        .split('\n')
        .map((line) => {
          const [hash, shortHash, author, authoredAt, subject] = line.split('\x1f');
          if (!hash || !shortHash || !author || !authoredAt || !subject) return null;
          return { hash, shortHash, author, authoredAt, subject };
        })
        .filter(Boolean)
    : [];
}

function getTotalCommitCount(paths = []) {
  const pathArgs = paths.length ? ` -- ${paths.map((p) => JSON.stringify(p)).join(' ')}` : '';
  const totalRaw = runGit(`git rev-list --count HEAD${pathArgs}`);
  const totalChanges = Number(totalRaw);
  return Number.isFinite(totalChanges) && totalChanges >= 0 ? totalChanges : 0;
}

function collectMarkdownFiles(rootDir) {
  const out = [];
  const stack = [rootDir];
  while (stack.length > 0) {
    const dir = stack.pop();
    if (!dir) continue;
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = path.posix.join(dir, entry.name);
      if (entry.isDirectory()) {
        stack.push(full);
        continue;
      }
      if (entry.isFile() && (full.endsWith('.md') || full.endsWith('.mdx'))) {
        out.push(full);
      }
    }
  }
  return out;
}

function contentPathFilters(filePath) {
  const base = filePath.replace(/\.(md|mdx)$/i, '');
  return Array.from(new Set([filePath, base, `${base}.md`, `${base}.mdx`]));
}

function safeWrite(payload) {
  writeFileSync(OUTPUT_PATH, JSON.stringify(payload, null, 2));
}

try {
  const commits = getRecentCommits();

  const totalChanges = getTotalCommitCount();

  const remote = runGit('git config --get remote.origin.url');
  const repoUrl = normalizeGitHubRepoUrl(remote);
  const pathMetadata = {};

  for (const contentDir of [BLOG_CONTENT_DIR, PROJECTS_CONTENT_DIR]) {
    for (const filePath of collectMarkdownFiles(contentDir)) {
      const filters = contentPathFilters(filePath);
      const slice = {
        commits: getRecentCommits(filters),
        totalChanges: getTotalCommitCount(filters),
      };
      for (const filter of filters) {
        pathMetadata[filter] = slice;
      }
    }
  }

  safeWrite({
    commits,
    totalChanges,
    repoUrl,
    pathMetadata,
  });
} catch {
  safeWrite({
    commits: [],
    totalChanges: 0,
    repoUrl: null,
    pathMetadata: {},
  });
}
