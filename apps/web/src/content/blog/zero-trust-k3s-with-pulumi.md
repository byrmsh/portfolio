---
title: 'Zero Trust K3s with Pulumi'
description: 'Hardening the homelab with Cilium, mTLS, and boringly-repeatable infra.'
pubDate: 2026-02-10
draft: true
tags: ['k3s', 'pulumi', 'cilium', 'homelab', 'security']
---

This post is a work in progress.

## What I'm building

- A K3s cluster that defaults to least-privilege networking.
- Service-to-service identity (mTLS) that doesn't rely on "trust the subnet".
- Infrastructure defined and repeatable via Pulumi.

## Notes

I'll expand this into a full write-up with:

- baseline cluster setup
- Cilium policy patterns
- cert / identity strategy
- troubleshooting and gotchas
