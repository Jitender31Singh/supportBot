from __future__ import annotations

import json

import pytest

from trackobit_assistant.app.streaming import chunk_text, format_sse_event, progress_label


def test_sse_event_round_trips_json_payload() -> None:
    encoded = format_sse_event("progress", {"label": "Checking status", "step": 2})
    assert encoded.startswith("event: progress\n")
    data_line = next(line[6:] for line in encoded.splitlines() if line.startswith("data: "))
    assert json.loads(data_line) == {"label": "Checking status", "step": 2}
    assert encoded.endswith("\n\n")


def test_chunk_text_reassembles_exact_original() -> None:
    value = "GPS location is not updating. Please send the STATUS# output.\nThanks!"
    chunks = list(chunk_text(value, chunk_size=7))
    assert len(chunks) > 1
    assert "".join(chunks) == value


def test_chunk_text_rejects_invalid_chunk_size() -> None:
    with pytest.raises(ValueError):
        list(chunk_text("answer", chunk_size=0))


def test_progress_labels_have_safe_fallback() -> None:
    assert progress_label("fetch_vehicle_info") == "Checking vehicle and device status…"
    assert progress_label("unexpected_new_node") == "Working through the next support step…"
