---
title: Homelab
description: GitOps-driven homelab automation with Ansible bootstrap and Argo CD delivery.
summary: Multi-node k3s homelab managed with Ansible + Argo CD and reproducible day-2 operations workflows.
year: 2026
stack:
  - Ansible
  - Kubernetes
  - Argo CD
  - Pulumi
heroImage: /projects/homelab/SS1.png
galleryImages:
  - /projects/homelab/SS1.png
order: 2
---

This is my infra repo for running and maintaining the cluster behind my projects. I moved critical bootstrap steps out of one-shot cloud-init and into Ansible roles so everything can be re-run cleanly.

It covers k3s setup, Argo CD installation, repo credentials, image updater wiring, and the app-of-apps flow. The main benefit is predictable operations: easier upgrades, easier rollbacks, and less hidden state.

I use this repo to practice the operational side of software, not just app development.
