#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Bump deploy/helm/portfolio/values-prod.yaml image tags to a given tag (e.g. git SHA)."
    )
    ap.add_argument("--tag", required=True, help="Image tag to set (e.g. git SHA)")
    ap.add_argument(
        "--file",
        default="deploy/helm/portfolio/values-prod.yaml",
        help="Values file to update",
    )
    args = ap.parse_args()

    try:
        from ruamel.yaml import YAML  # type: ignore
    except Exception as e:
        raise SystemExit(
            "Missing dependency: ruamel.yaml\n"
            "Install: python3 -m pip install --user ruamel.yaml"
        ) from e

    path = Path(args.file)
    data = path.read_text()

    yaml = YAML()
    yaml.preserve_quotes = True
    doc = yaml.load(data) or {}

    def set_path(d: dict, keys: list[str], value: str) -> None:
        cur = d
        for k in keys[:-1]:
            if k not in cur or cur[k] is None:
                cur[k] = {}
            cur = cur[k]
        cur[keys[-1]] = value

    # Top-level deployments
    set_path(doc, ["api", "image", "tag"], args.tag)
    set_path(doc, ["web", "image", "tag"], args.tag)

    # CronJobs (values are a list; bump every job image tag if present)
    jobs = (
        ((doc.get("collectorCronJobs") or {}).get("jobs") or [])
        if isinstance(doc, dict)
        else []
    )
    if isinstance(jobs, list):
        for j in jobs:
            if not isinstance(j, dict):
                continue
            img = j.get("image")
            if isinstance(img, dict):
                img["tag"] = args.tag

    out = Path(path)
    with out.open("w") as f:
        yaml.dump(doc, f)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

