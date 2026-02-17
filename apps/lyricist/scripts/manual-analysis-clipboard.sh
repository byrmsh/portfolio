#!/usr/bin/env bash
set -euo pipefail

SOURCE="missing"
BATCH_SIZE="10"
START_BATCH="1"
OUT_DIR=""
STRICT_IMPORT="true"
KEEP_FILES="false"
GEMINI_AUTO="false"
GEMINI_URL="https://gemini.google.com/app"
GEMINI_PROFILE_DIR="${HOME}/.cache/lyricist-gemini-playwright"
GEMINI_HEADLESS="false"
GEMINI_ALLOW_NEW_MESSAGE="false"

usage() {
  cat <<'EOF'
Interactive manual-analysis workflow for lyricist.

Generates batches, copies each prompt to clipboard, accepts pasted JSON responses,
then imports everything to Redis in one step at the end.

Usage:
  ./scripts/manual-analysis-clipboard.sh [options]

Options:
  --source pending|missing   Batch source passed to prepare-batch (default: missing)
  --batch-size N             Tracks per batch (default: 10)
  --start-batch N            First batch number (default: 1)
  --out-dir PATH             Session output directory (default: tmp/lyricist-batches/session-<timestamp>)
  --no-strict-import         Import without --strict
  --keep-files               Keep generated prepare-batch artifacts (default: prompt via stdout only)
  --gemini-auto              Send prompt to Gemini via Playwright, auto-capture response JSON
  --gemini-url URL           Gemini chat URL to automate (default: https://gemini.google.com/app)
  --gemini-profile-dir PATH  Chromium profile dir for Gemini login/session reuse
  --gemini-headless          Run Playwright browser headless
  --gemini-allow-new-message Allow fallback to new message if 'Edit prompt' button is unavailable
  -h, --help                 Show this help

Paste mode controls:
  :done   Finish current batch paste
  :skip   Skip current batch
  :quit   Finish session and import collected batches
  :abort  Exit without importing
EOF
}

sanitize_json_file() {
  local file="$1"
  local tmp="${file}.sanitized"

  # Remove ANSI/terminal escape sequences (e.g. ESC E / CSI codes from paste artifacts).
  perl -pe 's/\e(?:\[[0-9;?]*[ -\/]*[@-~]|[@-Z\\-_])//g' "$file" >"$tmp"

  # Strip markdown fences if user pasted a fenced block.
  sed -i '/^[[:space:]]*```/d' "$tmp"

  # Replace original with sanitized content.
  mv "$tmp" "$file"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
  --source)
    SOURCE="${2:-}"
    shift 2
    ;;
  --batch-size)
    BATCH_SIZE="${2:-}"
    shift 2
    ;;
  --start-batch)
    START_BATCH="${2:-}"
    shift 2
    ;;
  --out-dir)
    OUT_DIR="${2:-}"
    shift 2
    ;;
  --no-strict-import)
    STRICT_IMPORT="false"
    shift
    ;;
  --keep-files)
    KEEP_FILES="true"
    shift
    ;;
  --gemini-auto)
    GEMINI_AUTO="true"
    shift
    ;;
  --gemini-url)
    GEMINI_URL="${2:-}"
    shift 2
    ;;
  --gemini-profile-dir)
    GEMINI_PROFILE_DIR="${2:-}"
    shift 2
    ;;
  --gemini-headless)
    GEMINI_HEADLESS="true"
    shift
    ;;
  --gemini-allow-new-message)
    GEMINI_ALLOW_NEW_MESSAGE="true"
    shift
    ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    echo "Unknown arg: $1" >&2
    usage
    exit 1
    ;;
  esac
done

case "$SOURCE" in
pending | missing) ;;
*)
  echo "--source must be pending or missing" >&2
  exit 1
  ;;
esac

if ! [[ "$BATCH_SIZE" =~ ^[0-9]+$ ]] || [ "$BATCH_SIZE" -le 0 ]; then
  echo "--batch-size must be a positive integer" >&2
  exit 1
fi

if ! [[ "$START_BATCH" =~ ^[0-9]+$ ]] || [ "$START_BATCH" -le 0 ]; then
  echo "--start-batch must be a positive integer" >&2
  exit 1
fi

if [ -z "$OUT_DIR" ]; then
  ts="$(date +%Y%m%d-%H%M%S)"
  OUT_DIR="tmp/lyricist-batches/session-${ts}"
fi

mkdir -p "$OUT_DIR"
RESPONSES_DIR="$OUT_DIR/responses"
mkdir -p "$RESPONSES_DIR"
RESP_LIST="$OUT_DIR/response-files.txt"
: >"$RESP_LIST"
mkdir -p "$GEMINI_PROFILE_DIR"

if command -v wl-copy >/dev/null 2>&1; then
  CLIP_TOOL="wl-copy"
elif command -v xclip >/dev/null 2>&1; then
  CLIP_TOOL="xclip"
elif command -v pbcopy >/dev/null 2>&1; then
  CLIP_TOOL="pbcopy"
else
  CLIP_TOOL=""
fi

echo "Session dir: $OUT_DIR"
echo "Source: $SOURCE | batch size: $BATCH_SIZE | start batch: $START_BATCH"
if [ -n "$CLIP_TOOL" ]; then
  echo "Clipboard tool: $CLIP_TOOL"
else
  echo "No clipboard tool found. Prompt file path will be printed each round."
fi
if [ "$GEMINI_AUTO" = "true" ]; then
  echo "Gemini automation: enabled"
  echo "Gemini URL: $GEMINI_URL"
  echo "Gemini profile dir: $GEMINI_PROFILE_DIR"
fi

batch="$START_BATCH"
abort_session="false"

while true; do
  echo
  echo "Preparing batch $batch..."
  batch_id="$(printf "%03d" "$batch")"
  response_file="$RESPONSES_DIR/batch-${batch_id}.response.json"

  prompt_text=""
  if [ "$KEEP_FILES" = "true" ]; then
    prep_output="$(
      uv run lyricist-manual-analysis prepare-batch \
        --source "$SOURCE" \
        --batch-size "$BATCH_SIZE" \
        --batch-number "$batch" \
        --out-dir "$OUT_DIR" 2>&1
    )"
    if echo "$prep_output" | grep -q "No tracks found for this batch."; then
      echo "No tracks found for this batch."
      break
    fi
    prompt_file="$OUT_DIR/batch-${batch_id}.prompt.txt"
    if [ ! -f "$prompt_file" ]; then
      echo "Missing prompt file: $prompt_file" >&2
      exit 1
    fi
    prompt_text="$(cat "$prompt_file")"
  else
    set +e
    prompt_text="$(
      uv run lyricist-manual-analysis prepare-batch \
        --source "$SOURCE" \
        --batch-size "$BATCH_SIZE" \
        --batch-number "$batch" \
        --stdout-prompt \
        --no-files \
        --quiet
    )"
    prep_rc=$?
    set -e
    if [ "$prep_rc" -eq 3 ]; then
      echo "No tracks found for this batch."
      break
    fi
    if [ "$prep_rc" -ne 0 ]; then
      echo "prepare-batch failed with exit code $prep_rc" >&2
      exit "$prep_rc"
    fi
    if [ -z "$prompt_text" ]; then
      echo "Empty prompt returned for batch $batch_id." >&2
      exit 1
    fi
  fi

  echo "Batch $batch_id ready."
  prompt_file_runtime="$OUT_DIR/batch-${batch_id}.prompt.runtime.txt"
  printf '%s' "$prompt_text" >"$prompt_file_runtime"

  if [ "$GEMINI_AUTO" = "true" ]; then
    echo "Running Gemini Playwright automation for batch $batch_id..."
    auto_args=(
      --url "$GEMINI_URL"
      --user-data-dir "$GEMINI_PROFILE_DIR"
      --prompt-file "$prompt_file_runtime"
      --response-file "$response_file"
    )
    if [ "$GEMINI_HEADLESS" = "true" ]; then
      auto_args+=(--headless)
    fi
    if [ "$GEMINI_ALLOW_NEW_MESSAGE" = "true" ]; then
      auto_args+=(--allow-new-message)
    fi

    if uv run --with playwright python ./scripts/gemini_playwright.py "${auto_args[@]}"; then
      if [ -s "$response_file" ]; then
        sanitize_json_file "$response_file"
        if uv run lyricist-manual-analysis import-batch --file "$response_file" --dry-run --strict >/dev/null 2>&1; then
          echo "$response_file" >>"$RESP_LIST"
          echo "Validated Gemini response for batch $batch_id."
          batch=$((batch + 1))
          continue
        fi
        echo "Gemini response validation failed for batch $batch_id; falling back to manual paste."
      else
        echo "Gemini returned empty response for batch $batch_id; falling back to manual paste."
      fi
    else
      echo "Gemini automation failed for batch $batch_id; falling back to manual paste."
      echo "Hint: install browser binaries once with:"
      echo "  uv run --with playwright playwright install chromium"
    fi
  fi

  if [ -n "$CLIP_TOOL" ]; then
    if [ "$CLIP_TOOL" = "wl-copy" ]; then
      printf '%s' "$prompt_text" | wl-copy
    elif [ "$CLIP_TOOL" = "xclip" ]; then
      printf '%s' "$prompt_text" | xclip -selection clipboard
    else
      printf '%s' "$prompt_text" | pbcopy
    fi
    echo "Prompt copied to clipboard for batch $batch_id."
  else
    echo "No clipboard tool found. Prompt:"
    printf '%s\n' "$prompt_text"
  fi

  while true; do
    echo "Paste JSON response for batch $batch_id, then send ':done'."
    echo "Commands: :skip | :quit | :abort"
    : >"$response_file"
    mode="done"

    while IFS= read -r line; do
      case "$line" in
      :done)
        mode="done"
        break
        ;;
      :skip)
        mode="skip"
        break
        ;;
      :quit)
        mode="quit"
        break
        ;;
      :abort)
        mode="abort"
        break
        ;;
      *)
        printf '%s\n' "$line" >>"$response_file"
        ;;
      esac
    done

    if [ "$mode" = "skip" ]; then
      echo "Skipped batch $batch_id."
      rm -f "$response_file"
      break
    fi

    if [ "$mode" = "abort" ]; then
      abort_session="true"
      rm -f "$response_file"
      break 2
    fi

    if [ "$mode" = "quit" ]; then
      if [ ! -s "$response_file" ]; then
        rm -f "$response_file"
      fi
      break 2
    fi

    if [ ! -s "$response_file" ]; then
      echo "Response is empty. Paste again or :skip."
      continue
    fi

    sanitize_json_file "$response_file"

    if uv run lyricist-manual-analysis import-batch --file "$response_file" --dry-run --strict >/dev/null 2>&1; then
      echo "$response_file" >>"$RESP_LIST"
      echo "Validated batch $batch_id response."
      break
    fi

    echo "Validation failed for batch $batch_id. Paste again or :skip."
  done

  batch=$((batch + 1))
done

if [ "$abort_session" = "true" ]; then
  echo "Aborted. No DB import was performed."
  exit 0
fi

if [ ! -s "$RESP_LIST" ]; then
  echo "No validated responses collected. Nothing to import."
  exit 0
fi

COMBINED_FILE="$OUT_DIR/combined.response.json"
uv run python - "$RESP_LIST" "$COMBINED_FILE" <<'PY'
import json
import sys
from pathlib import Path

resp_list = Path(sys.argv[1]).read_text().splitlines()
combined = []
for p in resp_list:
    payload = json.loads(Path(p).read_text())
    if not isinstance(payload, list):
        raise ValueError(f"{p} must be a JSON array")
    combined.extend(payload)
Path(sys.argv[2]).write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n")
print(f"Combined entries: {len(combined)}")
PY

echo "Combined file: $COMBINED_FILE"
echo "Importing to Redis..."

import_args=(import-batch --file "$COMBINED_FILE")
if [ "$STRICT_IMPORT" = "true" ]; then
  import_args+=(--strict)
fi

uv run lyricist-manual-analysis "${import_args[@]}"
echo "Done."
