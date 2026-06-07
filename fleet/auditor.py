#!/usr/bin/env python3
"""Answer Auditor — the deterministic verification seam (Sentinel Mesh lineage).

Born from a real incident on day 0 of this build: an A2A worker crashed and the
orchestrator confidently fabricated a KRW price and 2024 chart timestamps. The
auditor makes that class of failure structurally impossible to ship:

  1. NUMERIC AUDIT (no model in the loop): every significant number in the final
     answer must appear in, or be within tolerance of, a number some tool actually
     returned this session. Unmatched money-scale numbers -> BLOCK.
  2. TRIPWIRE (vendored from Sentinel Mesh): buy/sell recommendations and
     money-movement language (EN+KR) -> BLOCK, regardless of what any model thinks.

Verdicts: pass | block. A blocked answer is replaced by an honest unavailability
message — a confident guess never reaches the user.
"""
import json
import re

# Sentinel Mesh lineage — finance-copilot edition (output-side gate).
TRIPWIRE = [
    r"\b(buy|sell) (now|today|immediately)\b", r"\bguaranteed (return|profit)\b",
    r"\byou should (buy|sell|invest)\b", r"\bwithdraw\b", r"\btransfer\b",
    r"매수하세요", r"매도하세요", r"사세요", r"파세요", r"투자하세요",
    r"수익(을|이)? 보장", r"확실(히|한) (수익|상승|하락)", r"출금해", r"송금해", r"이체해",
]

_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d{4,})(?![\w%])")


def _numbers(text):
    out = []
    for m in _NUM.finditer(text):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out


def _tool_numbers(tool_outputs):
    """Flatten every numeric value any tool returned this session."""
    nums = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, bool):
            pass
        elif isinstance(v, (int, float)):
            nums.add(float(v))
        elif isinstance(v, str):
            for n in _numbers(v):
                nums.add(n)

    for o in tool_outputs:
        walk(o)
    return nums


def audit(answer: str, tool_outputs: list, tolerance: float = 0.03) -> dict:
    """Audit a final answer against this session's actual tool outputs."""
    # 1. tripwire — deterministic, model-independent
    trips = sorted({p for p in TRIPWIRE if re.search(p, answer, re.I)})
    if trips:
        return {"verdict": "block", "reason": "tripwire", "tripwire": trips,
                "unmatched": [], "checked": 0}

    # 2. numeric audit (skip CHART_DATA blob — it is tool output passed through,
    #    and dates/years below money scale)
    body = re.sub(r"CHART_DATA:.*", "", answer, flags=re.S)
    claimed = [n for n in _numbers(body) if n >= 100]  # money-scale only
    truth = _tool_numbers(tool_outputs)
    unmatched = []
    for n in claimed:
        ok = any(t != 0 and abs(n - t) / max(abs(t), 1e-9) <= tolerance for t in truth) \
             or n in truth
        if not ok:
            unmatched.append(n)
    verdict = "block" if unmatched else "pass"
    return {"verdict": verdict, "reason": "unverified numbers" if unmatched else "",
            "tripwire": [], "unmatched": unmatched, "checked": len(claimed)}


BLOCK_MESSAGE = ("죄송해요 — 방금 답변의 수치가 실시간 데이터와 일치하지 않아 "
                 "전송을 막았어요. 데이터를 다시 확인한 뒤 정확한 값으로 알려드릴게요.")


if __name__ == "__main__":  # checkpoint: the day-0 incident must be caught
    fabricated = "현재 비트코인 가격은 95,845,000 원 입니다."
    real_tool = [{"symbol": "BTCUSD", "price": 61399.55, "open": 61392.75}]
    a = audit(fabricated, real_tool)
    honest = "비트코인은 현재 61,399.55 달러입니다."
    b = audit(honest, real_tool)
    advice = "지금 당장 매수하세요, 수익 보장됩니다."
    c = audit(advice, real_tool)
    print("fabricated ->", a["verdict"], a["unmatched"])
    print("honest     ->", b["verdict"])
    print("advice     ->", c["verdict"], c["tripwire"][:2])
    ok = a["verdict"] == "block" and b["verdict"] == "pass" and c["verdict"] == "block"
    print("CHECKPOINT:", "GREEN" if ok else "RED")
    raise SystemExit(0 if ok else 1)
