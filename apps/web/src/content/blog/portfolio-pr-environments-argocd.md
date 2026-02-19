---
title: 'PR Previews with Argo CD ApplicationSet'
description: 'How I run pull request preview environments with Argo CD so each PR gets its own URL and is cleaned up automatically'
pubDate: '19 Feb 2026'
heroImage: '../../assets/blog-placeholder-2.jpg'
tags:
  - Argo CD
  - ApplicationSet
  - Kubernetes
  - GitOps
---

This site uses temporary preview environments for pull requests.

When a PR is marked for preview, a dedicated environment is created with PR-specific URLs and images.
When that PR is no longer selected, the environment is removed automatically.

In this post, I’ll walk through how I set it up with Argo CD and what to change if you want to use the same approach.

### Why this pattern

For PR previews, the most useful setup is usually:

- one namespace per PR
- one Application per PR
- hostnames derived from PR number
- image tags derived from PR number + commit SHA
- automatic prune when the PR is no longer selected

Argo CD ApplicationSet gives this with one template and a pull request generator.

### 1. PR selection (label-gated)

This keeps previews opt-in and avoids creating environments for every open PR.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: app-pr
  namespace: argocd
spec:
  generators:
    - pullRequest:
        github:
          owner: <org>
          repo: <repo>
          tokenRef:
            secretName: <repo-credential-secret>
            key: password
          labels:
            - preview
        requeueAfterSeconds: 120
```

### 2. Template naming and destination

Use PR number as the stable key across resources.

```yaml
spec:
  template:
    metadata:
      name: 'app-pr-{{number}}'
    spec:
      destination:
        server: https://kubernetes.default.svc
        namespace: 'app-pr-{{number}}'
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
```

`prune: true` is what makes teardown automatic when a PR stops matching the generator.

### 3. Multi-source composition

A practical split is:

- app chart source (from PR ref)
- platform routing source (shared)
- preview bootstrap source (shared)
- values ref source (`$values/...`)

```yaml
sources:
  - repoURL: https://github.com/<org>/<app-repo>.git
    targetRevision: 'pull/{{number}}/head'
    path: deploy/helm/<chart>
    helm:
      releaseName: app
      valueFiles:
        - values.yaml
        - $values/k8s/<app>/values-pr.yaml
      parameters:
        - name: global.domain
          value: 'pr-{{number}}.<domain>'
        - name: global.apiHost
          value: 'api-pr-{{number}}.<domain>'
        - name: api.image.tag
          value: 'pr-{{number}}-{{head_sha}}'
        - name: web.image.tag
          value: 'pr-{{number}}-{{head_sha}}'

  - repoURL: https://github.com/<org>/<gitops-repo>.git
    targetRevision: main
    path: k8s/<app>/edge

  - repoURL: https://github.com/<org>/<gitops-repo>.git
    targetRevision: main
    path: k8s/<app>/preview-bootstrap

  - repoURL: https://github.com/<org>/<gitops-repo>.git
    targetRevision: main
    ref: values
```

This keeps app code/versioning in the app repo and shared cluster concerns in the GitOps repo.

### 4. Tag format and CI contract

If ApplicationSet renders tags as `pr-{{number}}-{{head_sha}}`, CI must publish that exact tag format.

Example for PR 42:

- `ghcr.io/<org>/<app>-api:pr-42-<commit_sha>`
- `ghcr.io/<org>/<app>-web:pr-42-<commit_sha>`

Without this contract, previews are created but fail at image pull/deploy time.

### 5. Routing contract

The template usually expects:

- `pr-<n>.<domain>` for web
- `api-pr-<n>.<domain>` for API

Two layers have to agree:

- edge routing (wildcard or equivalent)
- in-cluster ingress host rules

If host patterns differ between these layers, previews deploy but stay unreachable.

### 6. Bootstrap contract for preview namespaces

If previews need pull/runtime credentials, define a bootstrap step that runs before workloads.

The important part is not the exact job implementation; it is the contract:

- source secret names and namespaces are explicit
- target namespace is `app-pr-<number>`
- RBAC grants only the specific reads/writes required
- bootstrap completes before main pods start

### What this looks like in my repo

Current mapping:

- selector + template: `k8s/argocd/applications/portfolio-pr.yaml`
- preview values: `k8s/portfolio/values-pr.yaml`
- ingress templates: `k8s/portfolio/edge/templates/ingress.yaml`
- bootstrap resources: `k8s/portfolio/preview-bootstrap`

Rendered hostnames:

- `pr-<number>.bayram.sh`
- `api-pr-<number>.bayram.sh`

Rendered namespace/Application name:

- `portfolio-pr-<number>`

### Adaptation checklist

If you want to copy this pattern into another stack, update these first:

1. PR selector labels (`preview` or your own workflow label)
2. App source path/revision (`pull/{{number}}/head` only works for GitHub PR refs)
3. Host templates and domain
4. Image tag template + CI publish format
5. Secret/bootstrap source and target namespace contracts
6. Repo credentials used by generator and source fetch

After those six are aligned, the rest is mostly template plumbing.
