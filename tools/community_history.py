"""Keep source review evidence across partial scans and source outages."""
import json


def merge_review_history(previous, current):
    result = []
    seen = set()
    for row in [*(previous or []), *(current or [])]:
        key = json.dumps(row, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result
