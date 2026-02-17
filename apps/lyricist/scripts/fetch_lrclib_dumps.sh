#!/usr/bin/env bash
set -euo pipefail

LIST_URL="${LRCLIB_DUMPS_LIST_URL:-https://lrclib-db-dumps.bu3nnyut4y9jfkdg.workers.dev}"
BASE_URL="${LRCLIB_DUMPS_BASE_URL:-https://db-dumps.lrclib.net}"
OUT_DIR="${1:-apps/lyricist/scripts/tmp/lrclib/dumps}"

mkdir -p "$OUT_DIR"
manifest_path="$OUT_DIR/manifest.json"

echo "Fetching dump manifest: $LIST_URL"
curl -fsSL "$LIST_URL" -o "$manifest_path"

count=$(jq '.objects | length' "$manifest_path")
echo "Found $count dump object(s)"

jq -r '.objects[] | [.key, (.size|tostring), .uploaded] | @tsv' "$manifest_path" \
  | while IFS=$'\t' read -r key size uploaded; do
    out="$OUT_DIR/$key"
    echo "Downloading $key"
    echo "  size: $size bytes"
    echo "  uploaded: $uploaded"

    # Resume partial downloads automatically.
    curl -fL --retry 20 --retry-all-errors --retry-delay 3 \
      -C - "$BASE_URL/$key" -o "$out"

    got_size=$(wc -c < "$out" | tr -d ' ')
    echo "Saved: $out ($got_size bytes)"
  done

echo "Done. Manifest and dump files are in: $OUT_DIR"
