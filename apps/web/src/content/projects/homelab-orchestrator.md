---
title: Homelab Orchestrator
description: Unified self-hosted operations dashboard with GitOps deploy workflows.
summary: A control plane for self-hosted services with GitOps deploy flows, runbook links, and health snapshots.
status: Archive
stack:
  - TypeScript
  - Kubernetes
  - Pulumi
heroImage: /projects/homelab-orchestrator.svg
galleryImages:
  - /projects/homelab-orchestrator.svg
  - /projects/activity-stream-digest.svg
featured: true
order: 1
---

## Why this exists

I wanted one operational cockpit for deployments, service health, and runbook links instead of spreading context across many tabs.

## What it currently does

- Tracks environment health checks.
- Surfaces deployment metadata from git history.
- Shows key links for incident response.

## Planned upgrades

- Add per-service dependency mapping.
- Add deploy rollback snapshots.
