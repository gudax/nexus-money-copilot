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
# Two layers: explicit imperatives AND softer advisory phrasing ("looks like a
# buying opportunity", "오를 것 같아요") — recommendation is recommendation
# whether it arrives as a command or a nudge.
TRIPWIRE = [
    # explicit imperatives (EN + KR)
    r"\b(buy|sell) (now|today|immediately)\b", r"\bguaranteed (return|profit)\b",
    r"\byou should (buy|sell|invest)\b", r"\bwithdraw\b", r"\btransfer\b",
    r"매수하세요", r"매도하세요", r"사세요", r"파세요", r"투자하세요",
    r"수익(을|이)? 보장", r"확실(히|한) (수익|상승|하락)", r"출금해", r"송금해", r"이체해",
    # soft advisory phrasing (EN + KR). Negated/refusal forms must NOT trip —
    # "매도를 추천해 드릴 수 없습니다" is the copilot doing its job.
    r"\b(good|great|perfect) (time|opportunity|moment) to (buy|sell|invest)\b",
    r"(?<!cannot )(?<!can't )(?<!not )(?<!never )\brecommend (buying|selling|investing)\b",
    r"\bI('d| would) (buy|sell)\b",
    r"\bworth (buying|investing)\b",
    r"매수\s*기회", r"매도\s*기회",
    r"(매수|매도|투자)[를을]?\s*(추천|권장|고려)(?![^.\n]{0,12}(없|않|금지|어렵))",
    r"사는\s*게\s*좋", r"파는\s*게\s*좋", r"들어가는\s*게\s*좋", r"담아\s*보",
    r"오를\s*(것|거)\s*같", r"내릴\s*(것|거)\s*같",
    r"상승할\s*(것|거)\s*같", r"하락할\s*(것|거)\s*같",
]

_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d{4,})(?![\w%])")
# currency marker near a number -> money claim even below the 100 magnitude floor
# (a $77 stock price must be audited too). `(?<![가-힣])원` keeps 직원/원인 out.
_CCY = re.compile(r"[$€£¥₩]|달러|(?<![가-힣])원|유로|USD|KRW|EUR|USDT")
_NUM_ANY = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+)(?![\w%])")


def _numbers(text):
    out = []
    for m in _NUM.finditer(text):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out


def _claimed_numbers(body):
    """Numbers in the answer that must be backed by a tool: anything >= 100
    (money scale), plus currency-marked numbers >= 10 (sub-100 stock prices,
    FX-adjacent values). Small bare numbers (counts, deltas) stay exempt."""
    out = []
    for m in _NUM_ANY.finditer(body):
        try:
            n = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if n >= 100:
            out.append(n)
        elif n >= 10 and _CCY.search(body[max(0, m.start() - 6):m.end() + 6]):
            out.append(n)
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
    claimed = _claimed_numbers(body)
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

BLOCK_MESSAGE_ADVICE = ("죄송해요 — 매수·매도 판단을 권하는 표현이 감지되어 답변을 "
                        "차단했어요. 저는 투자 조언 대신 검증된 정보만 드려요. "
                        "시세·차트·계좌 현황은 얼마든지 물어보세요.")


def block_message(verdict: dict) -> str:
    """Reason-appropriate replacement for a blocked answer."""
    return BLOCK_MESSAGE_ADVICE if verdict.get("reason") == "tripwire" else BLOCK_MESSAGE


if __name__ == "__main__":  # checkpoint: the day-0 incident must be caught
    real_tool = [{"symbol": "BTCUSD", "price": 61399.55, "open": 61392.75}]
    cases = [
        # (name, answer, truth, expected_verdict)
        ("fabricated", "현재 비트코인 가격은 95,845,000 원 입니다.", real_tool, "block"),
        ("honest", "비트코인은 현재 61,399.55 달러입니다.", real_tool, "pass"),
        ("advice", "지금 당장 매수하세요, 수익 보장됩니다.", real_tool, "block"),
        # soft advisory phrasing must trip exactly like an imperative
        ("soft-advice-kr", "지금이 매수 기회로 보입니다.", real_tool, "block"),
        ("soft-advice-kr2", "비트코인은 더 오를 것 같아요.", real_tool, "block"),
        ("soft-advice-en", "It looks like a great time to buy.", real_tool, "block"),
        # sub-100 currency-marked prices are audited too (the $77 stock case)
        ("sub100-fabricated", "엔비디아는 현재 77.3 달러입니다.", real_tool, "block"),
        ("sub100-honest", "엔비디아는 현재 77.3 달러입니다.",
         real_tool + [{"symbol": "NVDA", "price": 77.3}], "pass"),
        # bare small numbers (counts) stay exempt — no false block
        ("count-exempt", "최근 48개 캔들 기준으로 보여드렸어요.", real_tool, "pass"),
        # refusal language must NOT trip (the copilot's own refusal phrasing —
        # both observed live phrasings)
        ("refusal-passes", "매수 또는 매도와 같은 투자 조언은 드릴 수 없습니다.", real_tool, "pass"),
        ("refusal-passes2", "저는 매수 또는 매도를 추천해 드릴 수 없습니다.", real_tool, "pass"),
        ("refusal-passes-en", "I cannot recommend buying or selling.", real_tool, "pass"),
        # ...but the affirmative forms still trip
        ("affirm-trips", "이 종목 매수를 추천합니다.", real_tool, "block"),
        ("affirm-trips-en", "I recommend buying Bitcoin here.", real_tool, "block"),
    ]
    failures = []
    for name, ans, truth, expected in cases:
        v = audit(ans, truth)
        status = "OK  " if v["verdict"] == expected else "FAIL"
        if v["verdict"] != expected:
            failures.append((name, expected, v["verdict"]))
        print(f"{status} {name:18s} expected={expected:5s} got={v['verdict']:5s} "
              f"unmatched={v['unmatched']} tripwire={v['tripwire'][:2]}")
    print("CHECKPOINT:", "GREEN" if not failures else f"RED {failures}")
    raise SystemExit(0 if not failures else 1)
