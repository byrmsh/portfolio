---
title: Prompt Lab
description: Experiment tracker for prompt strategies and model behavior.
summary: An experiment tracker for LLM prompt strategies with reproducible runs and side-by-side comparisons.
status: Archive
stack:
  - Node.js
  - Postgres
  - Docker
heroImage: /projects/prompt-lab.svg
galleryImages:
  - /projects/prompt-lab.svg
  - /projects/lyric-study-companion.svg
order: 4
---

## Why this exists

Prompt experiments are hard to compare over time unless runs are tracked with consistent context.

## What it currently does

- Stores run metadata and outputs.
- Compares prompts side by side.
- Tracks changes in quality signals.

## Planned upgrades

- Add automatic scoring from evaluation rubrics.
- Add prompt version diffs.
