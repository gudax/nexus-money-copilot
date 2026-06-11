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
import base64
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "fleet"))

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from google.adk.runners import InMemoryRunner
from google.genai import types

import auditor
import truth_log
import vision_tools
from orchestrator import orchestrator

app = FastAPI(title="NEXUS Money Copilot", docs_url=None, redoc_url=None)
STATIC = pathlib.Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_runner = InMemoryRunner(agent=orchestrator)


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    user_id: str = Field(default="demo", max_length=64)
    image_b64: str | None = Field(default=None, max_length=12_000_000)
    image_mime: str = Field(default="image/png", max_length=40)

VISION_FAIL = ("I couldn't read that screenshot. Could you upload it again "
               "with your holdings clearly visible?")


@app.get("/api/health")
def health():
    return {"ok": True, "fleet": ["markets", "account", "vision"], "audited": True}


@app.post("/v1/ask")
async def ask(body: AskIn):
    t0 = time.perf_counter()
    truth_pos = truth_log.position()  # this request's raw-tool window starts here
    session = await _runner.session_service.create_session(
        app_name=_runner.app_name, user_id=body.user_id)
    texts, tool_outputs, specialists = [], [], set()
    vision_tagged = []  # source-tagged vision payloads, for receipts

    # Vision path: read the screenshot (model), price it (deterministic code),
    # and hand the orchestrator ONLY pre-verified numbers to narrate. Both
    # outputs join tool_outputs, so the auditor holds the answer to them.
    question = body.question
    if body.image_b64:
        try:
            extract = vision_tools.extract_holdings(
                base64.b64decode(body.image_b64), body.image_mime)
            valuation = vision_tools.value_holdings(extract)
        except Exception:
            return {"answer": VISION_FAIL, "chart_data": None,
                    "audit": {"verdict": "pass", "reason": "vision unavailable, fail-closed",
                              "numbers_checked": 0, "specialists": ["vision"],
                              "elapsed_ms": round((time.perf_counter() - t0) * 1000)}}
        specialists.add("vision")
        tool_outputs += [extract, valuation]
        vision_tagged += [{"source": "vision:extract_holdings", "data": extract},
                          {"source": "vision:value_holdings", "data": valuation}]
        question = (
            "The user attached a portfolio screenshot, and the system has already "
            "read it and valued it.\n"
            f"[SCREENSHOT EXTRACT] {json.dumps(extract, ensure_ascii=False)}\n"
            f"[LIVE VALUATION — verified numbers computed by code] {json.dumps(valuation, ensure_ascii=False)}\n"
            "Rules: only quote the numbers present in the verified JSON above — never "
            "compute, sum, or convert anything yourself. Naturally point out the "
            "difference between the screenshot value and the current valuation. If any "
            "item is unpriced, honestly say its price couldn't be found.\n"
            "Answer in clear, plain English.\n"
            f"User question: {body.question}")

    async for ev in _runner.run_async(
            user_id=body.user_id, session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=question)])):
        if not ev.content or not ev.content.parts:
            continue
        for p in ev.content.parts:
            if p.text:
                texts.append(p.text)
            fr = getattr(p, "function_response", None)
            if fr is not None:
                specialists.add(fr.name)
    answer = "\n".join(t for t in texts if t).strip()

    # AUDIT TRUTH = raw exchange/account JSON captured at the worker tool seam
    # (truth_log) + the vision pipeline's pre-verified numbers. The A2A
    # function_response is worker PROSE — deliberately NOT in the truth set,
    # so a worker hallucination cannot vouch for itself. If a worker crashed
    # or fabricated without touching a tool, the window is empty and any
    # money-scale number in the answer fails the audit (fail closed).
    tagged = truth_log.read_since_tagged(truth_pos)
    tool_outputs += [t["data"] for t in tagged]

    # split chart payload out of the prose
    chart = None
    m = re.search(r"CHART_DATA:\s*(\[.*?\])", answer, re.S)
    if m:
        try:
            chart = json.loads(m.group(1))
        except ValueError:
            chart = None
        answer = answer.replace(m.group(0), "").strip()

    verdict = auditor.audit(answer, tool_outputs, tagged_outputs=vision_tagged + tagged)
    if verdict["verdict"] == "block":
        answer, chart = auditor.block_message(verdict), None

    return {
        "answer": answer,
        "chart_data": chart,
        "audit": {
            "verdict": verdict["verdict"],
            "reason": verdict.get("reason", ""),
            "numbers_checked": verdict.get("checked", 0),
            "specialists": sorted(specialists),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000),
            # a receipt per displayed number: the raw exchange field that proves it
            "receipts": verdict.get("receipts", []),
        },
    }


@app.get("/")
def index():
    f = STATIC / "index.html"
    return FileResponse(f) if f.exists() else {"service": "nexus-money-copilot", "try": "POST /v1/ask"}
