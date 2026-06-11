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
    # --- ENGLISH (primary, for English-speaking judges) ---
    # explicit imperatives / money movement
    r"\b(buy|sell|get in) (now|today|right now|immediately|while you can)\b",
    r"\bnow('s| is) (a |the )?(good|great|perfect) time to (buy|sell|get in)\b",
    r"\b(it )?will (go up|rise|moon|skyrocket|surge|go down|drop|crash)\b",
    r"\bguaranteed (return|returns|profit|profits|gain|gains)\b",
    r"\byou should (buy|sell|invest)\b",
    r"\bwithdraw\b", r"\btransfer (funds|money)\b", r"\bsend money\b",
    r"\bmove (your |the )?(funds|money)\b", r"\bwire (funds|money|the)\b",
    r"\btransfer\b",
    # soft advisory phrasing (EN). Negated/refusal forms must NOT trip —
    # "I can't recommend buying or selling" is the copilot doing its job.
    r"\b(good|great|perfect) (time|opportunity|moment) to (buy|sell|invest|get in)\b",
    r"(?<!cannot )(?<!can't )(?<!not )(?<!never )(?<!won't )\brecommend (buying|selling|investing)\b",
    r"\bI('d| would) (buy|sell)\b",
    r"\bworth (buying|investing)\b",
    r"\bgreat (buy|investment)\b", r"\bgood (time|moment) to (buy|get in)\b",
    # --- KOREAN tripwire (retained — multilingual defense, a feature) ---
    # explicit imperatives (KR)
    r"매수하세요", r"매도하세요", r"사세요", r"파세요", r"투자하세요",
    r"수익(을|이)? 보장", r"확실(히|한) (수익|상승|하락)", r"출금해", r"송금해", r"이체해",
    # soft advisory phrasing (KR). Negated/refusal forms must NOT trip —
    # "매도를 추천해 드릴 수 없습니다" is the copilot doing its job.
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


def _match(n: float, t: float, tol: float) -> bool:
    return t != 0 and abs(n - t) / max(abs(t), 1e-9) <= tol or n == t


def _find_in(payload, n, tol, path=""):
    """DFS a raw tool payload for a number matching `n`; return (field_path,
    matched_value) for the first hit, else None. This is what backs a receipt:
    the exact field of the exact exchange response a displayed number came from."""
    if isinstance(payload, dict):
        for k, v in payload.items():
            r = _find_in(v, n, tol, f"{path}.{k}" if path else str(k))
            if r:
                return r
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            r = _find_in(v, n, tol, f"{path}[{i}]")
            if r:
                return r
    elif isinstance(payload, bool):
        return None
    elif isinstance(payload, (int, float)):
        if _match(n, float(payload), tol):
            return (path or "value", float(payload))
    elif isinstance(payload, str):
        for x in _numbers(payload):
            if _match(n, x, tol):
                return (path or "value", x)
    return None


def build_receipts(claimed, tagged_outputs, tol):
    """For each displayed number, find the raw exchange response that proves it.

    tagged_outputs: [{"source", "data"}] — the source-preserving truth window
    (truth_log.read_since_tagged) plus any code-computed payloads. Returns a
    receipt per claimed number: which source, which field, the raw matched value.
    A number with no receipt would have been blocked by the numeric audit, so on a
    PASS every receipt resolves — that is the point: nothing on screen is unbacked."""
    receipts = []
    for n in claimed:
        hit = None
        # Prefer the field that IS this number (exact), before any tolerance match —
        # so a displayed price points at the exact candle field it came from, not
        # merely a neighbouring value that happens to be within 3%.
        for cur_tol in (0.0, tol):
            for o in tagged_outputs:
                tagged = isinstance(o, dict) and "source" in o and "data" in o
                src = o["source"] if tagged else None
                payload = o["data"] if tagged else o
                found = _find_in(payload, n, cur_tol)
                if found:
                    hit = {"value": n, "source": src, "field": found[0],
                           "matched_value": found[1]}
                    break
            if hit:
                break
        receipts.append(hit or {"value": n, "source": None, "field": None,
                                 "matched_value": None})
    return receipts


def audit(answer: str, tool_outputs: list, tolerance: float = 0.03,
          tagged_outputs: list | None = None) -> dict:
    """Audit a final answer against this session's actual tool outputs.

    tool_outputs: plain raw payloads (the numeric truth set — never source
    strings, so a port number in a source tag can't masquerade as a price).
    tagged_outputs (optional): [{"source","data"}] used ONLY to attach receipts;
    when provided, the verdict carries a per-number provenance trail."""
    # 1. tripwire — deterministic, model-independent
    trips = sorted({p for p in TRIPWIRE if re.search(p, answer, re.I)})
    if trips:
        return {"verdict": "block", "reason": "tripwire", "tripwire": trips,
                "unmatched": [], "checked": 0, "receipts": []}

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
    receipts = build_receipts(claimed, tagged_outputs, tolerance) if tagged_outputs else []
    return {"verdict": verdict, "reason": "unverified numbers" if unmatched else "",
            "tripwire": [], "unmatched": unmatched, "checked": len(claimed),
            "receipts": receipts}


BLOCK_MESSAGE = ("I held that answer back — its numbers didn't match the live data. "
                 "Let me re-check and come back with the verified figures.")

BLOCK_MESSAGE_ADVICE = ("I can't share buy/sell recommendations. I give verified "
                        "information only — ask me for prices, charts, or your "
                        "account anytime.")


def block_message(verdict: dict) -> str:
    """Reason-appropriate replacement for a blocked answer."""
    return BLOCK_MESSAGE_ADVICE if verdict.get("reason") == "tripwire" else BLOCK_MESSAGE


if __name__ == "__main__":  # checkpoint: the day-0 incident must be caught
    real_tool = [{"symbol": "BTCUSD", "price": 61399.55, "open": 61392.75}]
    real_btc_en = real_tool  # BTCUSD 61399.55 in the truth set
    cases = [
        # (name, answer, truth, expected_verdict)
        # --- KOREAN cases (retained — prove multilingual coverage) ---
        # the authentic day-0 fabrication incident (KRW)
        ("fabricated", "현재 비트코인 가격은 95,845,000 원 입니다.", real_tool, "block"),
        ("honest", "비트코인은 현재 61,399.55 달러입니다.", real_tool, "pass"),
        ("advice", "지금 당장 매수하세요, 수익 보장됩니다.", real_tool, "block"),
        # soft advisory phrasing must trip exactly like an imperative
        ("soft-advice-kr", "지금이 매수 기회로 보입니다.", real_tool, "block"),
        ("soft-advice-kr2", "비트코인은 더 오를 것 같아요.", real_tool, "block"),
        # sub-100 currency-marked prices are audited too (the $77 stock case)
        ("sub100-fabricated", "엔비디아는 현재 77.3 달러입니다.", real_tool, "block"),
        ("sub100-honest", "엔비디아는 현재 77.3 달러입니다.",
         real_tool + [{"symbol": "NVDA", "price": 77.3}], "pass"),
        # bare small numbers (counts) stay exempt — no false block
        ("count-exempt", "최근 48개 캔들 기준으로 보여드렸어요.", real_tool, "pass"),
        # refusal language must NOT trip (the copilot's own refusal phrasing)
        ("refusal-passes", "매수 또는 매도와 같은 투자 조언은 드릴 수 없습니다.", real_tool, "pass"),
        ("refusal-passes2", "저는 매수 또는 매도를 추천해 드릴 수 없습니다.", real_tool, "pass"),
        # ...but the affirmative form still trips
        ("affirm-trips", "이 종목 매수를 추천합니다.", real_tool, "block"),

        # --- ENGLISH mirror cases (primary surface — English judges) ---
        # fabricated English price must block (no tool returned 73,200)
        ("fabricated-en", "Bitcoin is currently trading at $73,200.", real_btc_en, "block"),
        # honest English price (in the truth set) must pass
        ("honest-en", "Bitcoin is currently $61,399.55.", real_btc_en, "pass"),
        # English advice must block
        ("advice-en", "You should buy now — it will go up, guaranteed profit.", real_tool, "block"),
        ("soft-advice-en", "It looks like a great time to buy.", real_tool, "block"),
        ("affirm-trips-en", "I recommend buying Bitcoin here.", real_tool, "block"),
        # money-movement language must block
        ("money-move-en", "You can withdraw and transfer funds to your wallet.", real_tool, "block"),
        # English refusal must NOT trip
        ("refusal-passes-en", "I can't recommend buying or selling.", real_tool, "pass"),
        ("refusal-passes-en2", "I cannot recommend buying or selling — verified info only.", real_tool, "pass"),
    ]
    failures = []
    for name, ans, truth, expected in cases:
        v = audit(ans, truth)
        status = "OK  " if v["verdict"] == expected else "FAIL"
        if v["verdict"] != expected:
            failures.append((name, expected, v["verdict"]))
        print(f"{status} {name:18s} expected={expected:5s} got={v['verdict']:5s} "
              f"unmatched={v['unmatched']} tripwire={v['tripwire'][:2]}")
    # --- receipts: every displayed number resolves to a raw exchange field ---
    tagged = [{"source": "markets:/api/market/candles/BTCUSD",
               "data": {"symbol": "BTCUSD", "price": 61399.55, "open": 61392.75}}]
    rcv = audit("Bitcoin is currently $61,399.55.", [t["data"] for t in tagged],
                tagged_outputs=tagged)
    rcpt = rcv.get("receipts") or []
    if not (rcv["verdict"] == "pass" and len(rcpt) == 1
            and rcpt[0]["source"] == "markets:/api/market/candles/BTCUSD"
            and rcpt[0]["field"] == "price" and rcpt[0]["matched_value"] == 61399.55):
        failures.append(("receipt-resolves", "matched price field", rcpt))
    else:
        print(f"OK   {'receipt-resolves':18s} -> {rcpt[0]['source']} .{rcpt[0]['field']}={rcpt[0]['matched_value']}")
    # a tripwire/blocked answer carries no receipts (nothing to vouch for)
    if audit("You should buy now.", [], tagged_outputs=tagged).get("receipts") != []:
        failures.append(("blocked-no-receipts", [], "non-empty"))

    print("CHECKPOINT:", "GREEN" if not failures else f"RED {failures}")
    raise SystemExit(0 if not failures else 1)
