---
title: Upwork Wizard
description: Automated Upwork job ingestion and Slack alerting pipeline.
summary: Python producer/consumer system using Upwork GraphQL, Redis Streams, LLM-assisted filtering, and Slack notifications.
year: 2025
stack:
  - Python
  - Redis Streams
  - OpenAI API
  - Slack API
heroImage: /projects/upwork-wizard/SS1.webp
galleryImages:
  - /projects/upwork-wizard/SS1.webp
  - /projects/upwork-wizard/SS2.webp
order: 4
---

I built this to stop wasting time on manual job-feed scanning. One service fetches jobs from Upwork GraphQL and writes them into Redis streams; another consumes, filters, enriches, and posts short alerts to Slack.

Most of the hard work was around real-world reliability: auth refresh issues, proxy failures, stream offsets, and alert quality tuning so relevant jobs are surfaced without spam.

It is one of my favorite automation projects because it solved a daily problem and stayed usable over time.
