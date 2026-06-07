#!/usr/bin/env python3
"""NEXUS Money Copilot service — the audited orchestrator as an HTTP API.

POST /v1/ask {question} ->
  {answer, chart_data?, audit: {verdict, checked, elapsed_ms, specialists}}

Every response passes the deterministic Answer Auditor before leaving the
process: numeric claims are matched against what the fleet's tools actually
returned this session, and advice/money-movement language is tripwired. A
blocked answer is replaced with an honest unavailability message — judges can
see the audit verdict on every card.

This is the Cloud Run service the Toss BFF targets via CHAT_BRAIN=adk.
"""
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "fleet"))

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from google.adk.runners import InMemoryRunner
from google.genai import types

import auditor
from orchestrator import orchestrator

app = FastAPI(title="NEXUS Money Copilot", docs_url=None, redoc_url=None)
STATIC = pathlib.Path(__file__).resolve().parent / "static"
_runner = InMemoryRunner(agent=orchestrator)


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    user_id: str = Field(default="demo", max_length=64)


@app.get("/healthz")
def healthz():
    return {"ok": True, "fleet": ["markets", "account"], "audited": True}


@app.post("/v1/ask")
async def ask(body: AskIn):
    t0 = time.perf_counter()
    session = await _runner.session_service.create_session(
        app_name=_runner.app_name, user_id=body.user_id)
    texts, tool_outputs, specialists = [], [], set()
    async for ev in _runner.run_async(
            user_id=body.user_id, session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=body.question)])):
        if not ev.content or not ev.content.parts:
            continue
        for p in ev.content.parts:
            if p.text:
                texts.append(p.text)
            fr = getattr(p, "function_response", None)
            if fr is not None:
                specialists.add(fr.name)
                try:
                    tool_outputs.append(fr.response if isinstance(fr.response, (dict, list))
                                        else json.loads(str(fr.response)))
                except (TypeError, ValueError):
                    tool_outputs.append({"raw": str(fr.response)[:2000]})
    answer = "\n".join(t for t in texts if t).strip()

    # split chart payload out of the prose
    chart = None
    m = re.search(r"CHART_DATA:\s*(\[.*?\])", answer, re.S)
    if m:
        try:
            chart = json.loads(m.group(1))
        except ValueError:
            chart = None
        answer = answer.replace(m.group(0), "").strip()

    verdict = auditor.audit(answer, tool_outputs)
    if verdict["verdict"] == "block":
        answer, chart = auditor.BLOCK_MESSAGE, None

    return {
        "answer": answer,
        "chart_data": chart,
        "audit": {
            "verdict": verdict["verdict"],
            "reason": verdict.get("reason", ""),
            "numbers_checked": verdict.get("checked", 0),
            "specialists": sorted(specialists),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000),
        },
    }


@app.get("/")
def index():
    f = STATIC / "index.html"
    return FileResponse(f) if f.exists() else {"service": "nexus-money-copilot", "try": "POST /v1/ask"}
