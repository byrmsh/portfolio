---
title: eToro Requester
description: Freelance automation bot for social-trading engagement workflows.
summary: Async Python service that tracks eToro events, posts replies, persists history in SQLite, and exposes 24h/7d reporting via Streamlit.
year: 2024
stack:
  - Python
  - aiohttp
  - SQLite
  - Streamlit
heroImage: /projects/etoro-requester/SS1.webp
galleryImages:
  - /projects/etoro-requester/SS1.webp
  - /projects/etoro-requester/SS2.webp
order: 5
---

This was a freelance automation project in the eToro domain, built for a high-volume account where reliability and low-noise behavior mattered.

The bot fetches notifications and copier events, posts pre-defined reply flows, and keeps a reliable SQLite history to prevent duplicate behavior. I also added a Streamlit reporting view for last-24h and last-7d activity.

The requirement was simple: run continuously, avoid noisy mistakes, and make activity auditable.
