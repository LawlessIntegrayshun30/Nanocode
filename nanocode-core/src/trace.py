from __future__ import annotations

import io
import json
from typing import Iterable, List

from src.runtime import Event


class JSONLTracer:
    """Simple tracer that writes JSONL event records to a file-like sink."""

    def __init__(self, sink: io.TextIOBase):
        self.sink = sink

    def __call__(self, event: Event) -> None:
        self.sink.write(json.dumps(event.to_record()))
        self.sink.write("\n")
        self.sink.flush()


def dump_events(events: Iterable[Event]) -> List[dict]:
    """Convert an event stream to JSON-serializable dicts."""

    return [ev.to_record() for ev in events]
