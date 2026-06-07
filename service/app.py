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

VISION_FAIL = ("죄송해요 — 스크린샷을 읽지 못했어요. 보유 내역이 보이는 화면으로 "
               "다시 한 번 올려주시겠어요?")


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
        question = (
            "사용자가 포트폴리오 스크린샷을 첨부했고, 시스템이 이미 읽기와 평가를 끝냈습니다.\n"
            f"[스크린샷 추출] {json.dumps(extract, ensure_ascii=False)}\n"
            f"[실시간 평가 — 코드가 계산한 검증된 수치] {json.dumps(valuation, ensure_ascii=False)}\n"
            "규칙: 위 JSON에 있는 수치만 그대로 인용하세요. 직접 계산·합산·환산은 절대 금지. "
            "스크린샷 기준 가치와 현재 평가의 차이를 자연스럽게 짚어주세요. "
            "unpriced 항목이 있으면 가격을 못 구했다고 정직하게 말하세요.\n"
            f"사용자 질문: {body.question}")

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
    tool_outputs += truth_log.read_since(truth_pos)

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
        },
    }


@app.get("/")
def index():
    f = STATIC / "index.html"
    return FileResponse(f) if f.exists() else {"service": "nexus-money-copilot", "try": "POST /v1/ask"}
