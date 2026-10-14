from typing import Any

def next_retry(counters: dict[str, int], step: str, max_retries: int) -> tuple[dict[str, int], bool, int]:
    updated = dict(counters)
    current = updated.get(step, 0) + 1
    updated[step] = current
    return updated, current < max_retries, current
