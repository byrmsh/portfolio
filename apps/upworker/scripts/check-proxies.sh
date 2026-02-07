#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 <input_proxies.txt> <output_good_proxies.txt> [test_url]" >&2
  exit 1
fi

INPUT_FILE="$1"
OUTPUT_FILE="$2"
TEST_URL="${3:-https://www.upwork.com/nx/search/jobs?page=2}"

if [[ ! -f "$INPUT_FILE" ]]; then
  echo "Input file not found: $INPUT_FILE" >&2
  exit 1
fi

TMP_OUTPUT="$(mktemp)"
trap 'rm -f "$TMP_OUTPUT"' EXIT

TIMEOUT_SECONDS="${PROXY_CHECK_TIMEOUT_SECONDS:-10}"
USER_AGENT="${PROXY_CHECK_USER_AGENT:-Mozilla/5.0 (X11; Linux x86_64)}"

checked=0
accepted=0
rejected=0

while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
  proxy="$(echo "$raw_line" | sed -e 's/^\s*//' -e 's/\s*$//')"
  if [[ -z "$proxy" || "$proxy" == \#* ]]; then
    continue
  fi

  checked=$((checked + 1))

  http_code="$({
    curl -sS -o /dev/null \
      -A "$USER_AGENT" \
      --max-time "$TIMEOUT_SECONDS" \
      --proxy "$proxy" \
      -w '%{http_code}' \
      "$TEST_URL"
  } 2>/dev/null || true)"

  if [[ "$http_code" =~ ^[0-9]{3}$ ]] && ((http_code >= 200 && http_code < 400)); then
    echo "$proxy" >> "$TMP_OUTPUT"
    accepted=$((accepted + 1))
    printf 'ok   %-4s %s\n' "$http_code" "$proxy"
  else
    rejected=$((rejected + 1))
    if [[ -z "$http_code" ]]; then
      http_code="err"
    fi
    printf 'drop %-4s %s\n' "$http_code" "$proxy"
  fi
done < "$INPUT_FILE"

mv "$TMP_OUTPUT" "$OUTPUT_FILE"

echo
echo "Checked:  $checked"
echo "Accepted: $accepted"
echo "Rejected: $rejected"
echo "Output:   $OUTPUT_FILE"
