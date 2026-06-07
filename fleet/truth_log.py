#!/usr/bin/env python3
"""Raw-tool-truth log — the auditor's ground-truth channel.

The fleet runs as three processes in one container (launcher.sh). Workers fetch
LMX JSON inside their own process, so the orchestrator's event stream only ever
carries worker PROSE — an A2A AgentTool returns the worker's narrated text, not
the raw numbers underneath it. Auditing prose against prose would let a worker
hallucination poison both sides of the check.

So every worker HTTP tool seam appends its raw JSON response here, and the
service unions the entries appended during a request into the auditor's truth
set: the numbers the user sees are matched against what the EXCHANGE returned,
not against what a model said the exchange returned. The model never gets a
chance to launder a number between the API and the audit.

Correlation is by file offset captured at request start — appropriate for the
single-container demo (one shared filesystem, low concurrency); a production
deployment would propagate trace IDs through the A2A call instead.
"""
import json
import os
import pathlib
import threading
import time

PATH = pathlib.Path(os.environ.get("TOOL_TRUTH_LOG", "/tmp/tool_truth.jsonl"))
_lock = threading.Lock()


def record(source: str, payload) -> None:
    """Append one raw tool response. Must never break a tool call."""
    try:
        line = json.dumps({"ts": time.time(), "source": source, "data": payload},
                          ensure_ascii=False, default=str)
        with _lock:
            with PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:  # noqa: BLE001 — the auditor fails closed without us anyway
        pass


def position() -> int:
    """Current end-of-log offset; capture at request start."""
    try:
        return PATH.stat().st_size
    except FileNotFoundError:
        return 0


def read_since(offset: int) -> list:
    """All raw payloads appended after `offset` (this request's tool window)."""
    out = []
    try:
        with PATH.open("r", encoding="utf-8") as f:
            f.seek(offset)
            for line in f:
                try:
                    out.append(json.loads(line)["data"])
                except (ValueError, KeyError):
                    pass
    except FileNotFoundError:
        pass
    return out
