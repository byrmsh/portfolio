import { execSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const RECENT_LIMIT = 3;
const OUTPUT_PATH = 'apps/web/dist/git-meta.json';
const LOG_FORMAT = '%H%x1f%h%x1f%aN%x1f%aI%x1f%s';

function normalizeGitHubRepoUrl(remote) {
  const trimmed = String(remote ?? '').trim().replace(/\.git$/, '');
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

function safeWrite(payload) {
  writeFileSync(OUTPUT_PATH, JSON.stringify(payload, null, 2));
}

try {
  const rawLog = runGit(`git log -n ${RECENT_LIMIT} --date=iso-strict --pretty=format:${LOG_FORMAT}`);
  const commits = rawLog
    ? rawLog
        .split('\n')
        .map((line) => {
          const [hash, shortHash, author, authoredAt, subject] = line.split('\x1f');
          if (!hash || !shortHash || !author || !authoredAt || !subject) return null;
          return { hash, shortHash, author, authoredAt, subject };
        })
        .filter(Boolean)
    : [];

  const totalRaw = runGit('git rev-list --count HEAD');
  const totalChanges = Number(totalRaw);

  const remote = runGit('git config --get remote.origin.url');
  const repoUrl = normalizeGitHubRepoUrl(remote);

  safeWrite({
    commits,
    totalChanges: Number.isFinite(totalChanges) && totalChanges >= 0 ? totalChanges : 0,
    repoUrl,
  });
} catch {
  safeWrite({
    commits: [],
    totalChanges: 0,
    repoUrl: null,
  });
}
