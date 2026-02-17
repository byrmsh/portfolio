#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Locator, TimeoutError, sync_playwright

DEFAULT_URL = "https://gemini.google.com/app"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)


def _sanitize_response(path: Path) -> None:
    text = path.read_text() if path.exists() else ""
    if not text:
        return
    text = re.sub(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|[@-Z\\-_])", "", text)
    text = "\n".join(line for line in text.splitlines() if not re.match(r"^\s*```", line))
    text = text.strip()
    if not text:
        path.write_text("")
        return

    # Gemini may wrap JSON with prose (e.g. "Gemini said ...").
    # Keep only the first valid top-level JSON array payload.
    start = text.find("[")
    if start == -1:
        path.write_text(text)
        return

    candidate = text[start:]
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, list):
            path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n")
            return
    except Exception:
        pass

    depth = 0
    in_str = False
    escaped = False
    end_idx = -1
    for idx, ch in enumerate(candidate):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue
        if ch == "[":
            depth += 1
            continue
        if ch == "]":
            depth -= 1
            if depth == 0:
                end_idx = idx
                break

    if end_idx == -1:
        path.write_text(text)
        return

    candidate = candidate[: end_idx + 1]
    try:
        parsed = json.loads(candidate)
    except Exception:
        path.write_text(text)
        return
    if isinstance(parsed, list):
        path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n")
    else:
        path.write_text(text)


def _first_visible(locator: Locator) -> Locator | None:
    for i in range(locator.count()):
        node = locator.nth(i)
        if node.is_visible():
            return node
    return None


def _last_visible(locator: Locator) -> Locator | None:
    for i in range(locator.count() - 1, -1, -1):
        node = locator.nth(i)
        if node.is_visible():
            return node
    return None


def _click_edit_prompt(page) -> bool:
    edit = _last_visible(page.get_by_role("button", name=re.compile("edit prompt", re.I)))
    if edit:
        edit.click()
        return True

    edit_css = _last_visible(page.locator("button[aria-label='Edit prompt'], button[mattooltip='Edit prompt']"))
    if edit_css:
        edit_css.click()
        return True

    return False


def _has_edit_prompt(page) -> bool:
    edit = _last_visible(page.get_by_role("button", name=re.compile("edit prompt", re.I)))
    if edit:
        return True
    edit_css = _last_visible(page.locator("button[aria-label='Edit prompt'], button[mattooltip='Edit prompt']"))
    return bool(edit_css)


def _click_new_chat(page) -> None:
    before_url = page.url
    new_chat = _first_visible(page.get_by_role("button", name=re.compile("new chat", re.I)))
    if new_chat:
        new_chat.click()
    else:
        # Gemini advertises Ctrl+Shift+O for new chat.
        page.keyboard.press("ControlOrMeta+Shift+O")

    try:
        page.wait_for_timeout(800)
        page.wait_for_function(
            "(u) => window.location.href !== u",
            before_url,
            timeout=15000,
        )
    except Exception:
        # Some variants keep /app until first send; this is acceptable.
        pass


def _chat_like_url(url: str) -> bool:
    return url.startswith("https://gemini.google.com/app")


def _user_message_count(page) -> int:
    value = page.evaluate(
        """
() => {
  const selectors = [
    'user-query',
    'query-container user-query',
    'query-container',
    'conversation-turn user-query'
  ];
  let maxCount = 0;
  for (const s of selectors) {
    const count = document.querySelectorAll(s).length;
    if (count > maxCount) maxCount = count;
  }
  return maxCount;
}
"""
    )
    try:
        return int(value)
    except Exception:
        return 0


def _resolve_chat_url(cache_file: Path, explicit_url: str | None) -> str | None:
    if explicit_url:
        return explicit_url.strip()
    if cache_file.exists():
        raw = cache_file.read_text().strip()
        if raw:
            return raw
    return None


def _persist_chat_url(cache_file: Path, page_url: str) -> None:
    if not _chat_like_url(page_url):
        return
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(page_url + "\n")


def _set_prompt_text(page, prompt: str) -> None:
    editor = _last_visible(
        page.locator(
            "div[contenteditable='true'][role='textbox'][aria-label*='prompt'], "
            "rich-textarea .ql-editor[contenteditable='true'][role='textbox']"
        )
    )
    if not editor:
        raise RuntimeError("Could not find Gemini prompt editor.")

    editor.click()
    page.keyboard.press("ControlOrMeta+A")
    page.keyboard.press("Backspace")
    page.keyboard.insert_text(prompt)


def _click_send(page) -> None:
    deadline = time.time() + 30
    send_locator = page.get_by_role("button", name=re.compile("send message", re.I))
    while time.time() < deadline:
        btn = _last_visible(send_locator)
        if btn and btn.is_enabled():
            btn.click()
            return
        time.sleep(0.2)
    raise RuntimeError("Send button is not available or enabled.")


def _latest_response_text(page) -> str:
    value = page.evaluate(
        """
() => {
  const nodes = Array.from(document.querySelectorAll('model-response response-container, model-response'));
  if (!nodes.length) return '';
  const node = nodes[nodes.length - 1];
  return (node.innerText || '').trim();
}
"""
    )
    return value.strip() if isinstance(value, str) else ""


def _copy_latest_response(page) -> None:
    copy_btn = _last_visible(page.get_by_role("button", name=re.compile("copy response", re.I)))
    if copy_btn and copy_btn.is_enabled():
        copy_btn.click()
        return

    copy_css = _last_visible(page.locator("button[aria-label='Copy response'], button[mattooltip='Copy response']"))
    if copy_css and copy_css.is_enabled():
        copy_css.click()


def _wait_for_generation(page, timeout_sec: int, stable_sec: int) -> str:
    deadline = time.time() + timeout_sec
    stable_deadline = 0.0
    last_text = ""

    while time.time() < deadline:
        text = _latest_response_text(page)
        stop_btn = _first_visible(page.get_by_role("button", name=re.compile("stop", re.I)))
        is_generating = bool(stop_btn and stop_btn.is_enabled())

        if text and text != last_text:
            last_text = text
            stable_deadline = time.time() + stable_sec

        if text and not is_generating and stable_deadline and time.time() >= stable_deadline:
            return text

        time.sleep(0.5)

    raise TimeoutError(f"Timed out after {timeout_sec}s while waiting for Gemini response.")


def _prepare_batch(cwd: Path, source: str, batch_size: int, batch_number: int) -> str | None:
    cmd = [
        "uv",
        "run",
        "lyricist-manual-analysis",
        "prepare-batch",
        "--source",
        source,
        "--batch-size",
        str(batch_size),
        "--batch-number",
        str(batch_number),
        "--stdout-prompt",
        "--no-files",
        "--quiet",
    ]
    cp = _run(cmd, cwd)
    if cp.returncode == 3:
        return None
    if cp.returncode != 0:
        raise RuntimeError(f"prepare-batch failed ({cp.returncode}): {cp.stderr.strip()}")
    if not cp.stdout.strip():
        raise RuntimeError("prepare-batch returned empty prompt")
    return cp.stdout


def _validate_response(cwd: Path, response_file: Path) -> bool:
    cmd = [
        "uv",
        "run",
        "lyricist-manual-analysis",
        "import-batch",
        "--file",
        str(response_file),
        "--dry-run",
        "--strict",
    ]
    cp = _run(cmd, cwd)
    return cp.returncode == 0


def _import_combined(cwd: Path, combined_file: Path, strict: bool) -> None:
    cmd = [
        "uv",
        "run",
        "lyricist-manual-analysis",
        "import-batch",
        "--file",
        str(combined_file),
    ]
    if strict:
        cmd.append("--strict")
    cp = _run(cmd, cwd)
    if cp.returncode != 0:
        raise RuntimeError(f"import-batch failed ({cp.returncode}):\n{cp.stdout}\n{cp.stderr}")
    if cp.stdout.strip():
        print(cp.stdout.strip())


def run(args: argparse.Namespace) -> int:
    app_dir = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out_dir) if args.out_dir else app_dir / "tmp" / "lyricist-batches" / f"session-{time.strftime('%Y%m%d-%H%M%S')}"
    responses_dir = out_dir / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)

    profile_dir = Path(args.gemini_profile_dir).expanduser()
    profile_dir.mkdir(parents=True, exist_ok=True)
    chat_url_cache = (
        Path(args.gemini_chat_url_cache).expanduser()
        if args.gemini_chat_url_cache
        else profile_dir / "chat_url.txt"
    )
    configured_chat_url = _resolve_chat_url(chat_url_cache, args.gemini_chat_url)

    print(f"Session dir: {out_dir}")
    print(f"Source: {args.source} | batch size: {args.batch_size} | start batch: {args.start_batch}")
    print(f"Gemini base URL: {args.gemini_url}")
    print(f"Gemini profile dir: {profile_dir}")
    print(f"Gemini chat URL cache: {chat_url_cache}")

    response_files: list[Path] = []
    batch = args.start_batch

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=args.gemini_headless,
            viewport={"width": 1500, "height": 1100},
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            if configured_chat_url:
                page.goto(configured_chat_url, wait_until="domcontentloaded")
            else:
                page.goto(args.gemini_url, wait_until="domcontentloaded")
            page.wait_for_selector("rich-textarea .ql-editor[contenteditable='true'][role='textbox']", timeout=90000)
            if not configured_chat_url:
                _click_new_chat(page)

            _persist_chat_url(chat_url_cache, page.url)
            seeded_chat = _has_edit_prompt(page)

            while True:
                batch_id = f"{batch:03d}"
                print(f"\nPreparing batch {batch}...")
                prompt = _prepare_batch(app_dir, args.source, args.batch_size, batch)
                if prompt is None:
                    print("No tracks found for this batch.")
                    break

                prompt_file = out_dir / f"batch-{batch_id}.prompt.runtime.txt"
                response_file = responses_dir / f"batch-{batch_id}.response.json"
                prompt_file.write_text(prompt)

                user_count_before = _user_message_count(page)
                require_edit = seeded_chat
                edited = _click_edit_prompt(page)
                if require_edit and not edited:
                    if not args.gemini_allow_new_message:
                        raise RuntimeError(
                            "Expected to edit the existing prompt, but 'Edit prompt' was not found. "
                            "Open the cached chat and ensure the previous prompt is visible, "
                            "or pass --gemini-allow-new-message."
                        )
                    print(f"Warning: batch {batch_id} is sending as a new message because edit mode was unavailable.")

                _set_prompt_text(page, prompt)
                _click_send(page)
                response = _wait_for_generation(page, timeout_sec=args.timeout_sec, stable_sec=args.stable_sec)
                _copy_latest_response(page)
                response_file.write_text(response)
                _sanitize_response(response_file)
                _persist_chat_url(chat_url_cache, page.url)
                user_count_after = _user_message_count(page)

                if require_edit and user_count_after > user_count_before:
                    raise RuntimeError(
                        f"Batch {batch_id} created a new user message instead of editing the existing one. "
                        "Stopping to avoid drift."
                    )

                if not response_file.read_text().strip():
                    raise RuntimeError(f"Gemini returned empty response for batch {batch_id}")

                if not _validate_response(app_dir, response_file):
                    raise RuntimeError(f"Validation failed for batch {batch_id}: {response_file}")

                response_files.append(response_file)
                print(f"Validated batch {batch_id}: {response_file}")
                seeded_chat = True
                batch += 1
        finally:
            context.close()

    if not response_files:
        print("No validated responses collected. Nothing to import.")
        return 0

    combined: list[dict] = []
    for rf in response_files:
        payload = json.loads(rf.read_text())
        if not isinstance(payload, list):
            raise RuntimeError(f"{rf} must contain a JSON array")
        combined.extend(payload)

    combined_file = out_dir / "combined.response.json"
    combined_file.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n")
    print(f"Combined entries: {len(combined)}")
    print(f"Combined file: {combined_file}")
    print("Importing to Redis...")
    _import_combined(app_dir, combined_file, strict=not args.no_strict_import)
    print("Done.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="End-to-end Gemini Playwright manual analysis runner")
    p.add_argument("--source", choices=["pending", "missing"], default="missing")
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument("--start-batch", type=int, default=1)
    p.add_argument("--out-dir", help="Session output directory")
    p.add_argument("--no-strict-import", action="store_true", help="Import without --strict")

    p.add_argument("--gemini-url", default=DEFAULT_URL)
    p.add_argument("--gemini-chat-url", help="Specific existing Gemini chat URL to reuse")
    p.add_argument(
        "--gemini-chat-url-cache",
        help="Path to chat URL cache file (default: <profile_dir>/chat_url.txt)",
    )
    p.add_argument("--gemini-profile-dir", default="~/.cache/lyricist-gemini-playwright")
    p.add_argument("--gemini-headless", action="store_true")
    p.add_argument("--gemini-allow-new-message", action="store_true")
    p.add_argument("--timeout-sec", type=int, default=420)
    p.add_argument("--stable-sec", type=int, default=3)
    return p


if __name__ == "__main__":
    parser = build_parser()
    ns = parser.parse_args()
    try:
        raise SystemExit(run(ns))
    except Exception as exc:
        print(f"manual-analysis-gemini error: {exc}", file=sys.stderr)
        raise SystemExit(1)
