// scripts/find-unused-keys.js
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// 1. Load your translations file
// Note: We are doing a rough regex parse to avoid compiling TS in this script.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TRANS_FILE = path.join(__dirname, '../apps/web/src/i18n/translations.ts');
const SRC_DIR = path.join(__dirname, '../apps/web/src');

// Helper: Flatten the object keys (e.g. { nav: { home: 'x' } } -> ['nav.home'])
function flattenKeys(obj, prefix = '') {
  let keys = [];
  for (const key in obj) {
    if (typeof obj[key] === 'object' && obj[key] !== null) {
      keys = keys.concat(flattenKeys(obj[key], prefix + key + '.'));
    } else {
      keys.push(prefix + key);
    }
  }
  return keys;
}

// Helper: Extract and parse the 'en' translations object from TypeScript file
function extractEnglishKeys() {
  const content = fs.readFileSync(TRANS_FILE, 'utf-8');

  // Find the 'en: { ... }' block
  // Match: en: { followed by everything until the closing brace (handling nested braces)
  const enMatch = content.match(/en:\s*\{([\s\S]*?)\n  \},/);
  if (!enMatch) {
    throw new Error('Could not find "en" translations object in ' + TRANS_FILE);
  }

  // The block includes the content but not the outer braces
  let enContent = '{' + enMatch[1] + '}';

  // Convert TypeScript object to valid JSON by:
  // 1. Removing line comments
  // 2. Removing block comments
  // 3. Converting single-quoted strings to double-quoted
  // 4. Removing trailing commas
  enContent = enContent
    .replace(/\/\/.*$/gm, '') // Remove line comments
    .replace(/\/\*[\s\S]*?\*\//g, '') // Remove block comments
    .replace(/,(\s*[}\]])/g, '$1'); // Remove trailing commas

  // Convert single quotes to double quotes for string values
  // This is tricky because we need to handle escaped quotes inside strings
  // Simple approach: replace patterns like: 'string' with "string"
  let jsonContent = enContent.replace(/'([^']|\\')*'/g, (match) => {
    // Convert the matched single-quoted string to double quotes
    return '"' + match.slice(1, -1).replace(/\\'/g, "'").replace(/"/g, '\\"') + '"';
  });

  // Quote unquoted keys (handle keys that don't have quotes)
  jsonContent = jsonContent.replace(/([{,]\s*)(\w+)(\s*:)/g, '$1"$2"$3');

  try {
    const enObj = JSON.parse(jsonContent);
    return flattenKeys(enObj);
  } catch (e) {
    console.error('Failed to parse English translations.');
    console.error('Parsed JSON:', jsonContent.substring(0, 500));
    throw e;
  }
}

// 2. Extract keys from translations.ts using regex and JSON parsing
const definedKeys = extractEnglishKeys();

// 3. Scan files
function getAllFiles(dirPath, arrayOfFiles) {
  const files = fs.readdirSync(dirPath);
  arrayOfFiles = arrayOfFiles || [];

  files.forEach(function (file) {
    if (fs.statSync(dirPath + '/' + file).isDirectory()) {
      arrayOfFiles = getAllFiles(dirPath + '/' + file, arrayOfFiles);
    } else {
      if (
        file.endsWith('.astro') ||
        file.endsWith('.svelte') ||
        file.endsWith('.ts') ||
        file.endsWith('.tsx')
      ) {
        arrayOfFiles.push(path.join(dirPath, '/', file));
      }
    }
  });

  return arrayOfFiles;
}

const files = getAllFiles(SRC_DIR);
console.log(`Scanning ${files.length} files in ${SRC_DIR}...`);

let usedKeys = new Set();
let fileContents = files.map((f) => fs.readFileSync(f, 'utf-8')).join('\n');

// 4. Check usage
const unused = [];

definedKeys.forEach((key) => {
  // We look for the key string literally.
  // This covers: t('key'), t("key"), keys.key, etc.
  // It might miss dynamic keys like `nav.${variable}`, but that's rare in typed dicts.
  // We explicitly check for the last part of the key to be looser (e.g. just 'httpError' if destructured)
  // But strictly looking for the full path is safer to avoid false positives.

  const keyParts = key.split('.');
  const lastPart = keyParts[keyParts.length - 1];

  // Regex: Look for the exact key string enclosed in quotes OR just the usage of the property
  // Simple includes check is usually sufficient for unique enough keys
  if (!fileContents.includes(key)) {
    // If full key not found, check if it might be used in a map/loop via the last part
    // (This is risky, usually better to report it as potential unused)
    unused.push(key);
  } else {
    usedKeys.add(key);
  }
});

console.log('\n--- POTENTIALLY UNUSED KEYS ---');
unused.forEach((k) => console.log(k));
console.log(`\nFound ${unused.length} unused keys out of ${definedKeys.length}.`);
