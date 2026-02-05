from __future__ import annotations

from _common import emit_event, logger, redis_client, write_metric


# Placeholder for cluster metrics ingestion.

def main() -> None:
    logger.info("collector.cluster.todo")
    r = redis_client()
    key = "metric:cluster:status"
    write_metric(r, key, {"status": "todo"})
    emit_event(r, "cluster_status_updated", {"key": key})


if __name__ == "__main__":
    main()
