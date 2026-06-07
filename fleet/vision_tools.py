#!/usr/bin/env python3
"""Vision pipeline — portfolio screenshot in, audited numbers out.

The model is only ever trusted to READ, never to compute:

  1. EXTRACT (model): Gemini vision pulls structured holdings out of the
     screenshot — names, quantities, reported values. Anything unreadable is
     null; the schema forbids invented numbers.
  2. VALUE (deterministic): plain Python maps holdings to LMX instruments and
     prices them with live quotes — qty x price happens in code, not in a model.
  3. Both outputs join the session's tool_outputs, so the Answer Auditor holds
     the final narration to exactly these numbers. A model that "remembers" a
     price or does its own arithmetic gets blocked at the door.
"""
import json

from google import genai
from google.genai import types

import markets_tools as mt

MODEL = "gemini-flash-latest"

_EXTRACT_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "platform_guess": types.Schema(type=types.Type.STRING,
                                       description="App/exchange the screenshot is from, or 'unknown'."),
        "holdings": types.Schema(type=types.Type.ARRAY, items=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "name": types.Schema(type=types.Type.STRING),
                "symbol_guess": types.Schema(type=types.Type.STRING,
                                             description="Ticker-style guess, e.g. BTC, ETH, XAU, AAPL."),
                "quantity": types.Schema(type=types.Type.NUMBER, nullable=True),
                "reported_value": types.Schema(type=types.Type.NUMBER, nullable=True),
                "currency": types.Schema(type=types.Type.STRING, nullable=True),
            },
            required=["name", "symbol_guess"],
        )),
        "account_totals": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "balance": types.Schema(type=types.Type.NUMBER, nullable=True),
                "equity": types.Schema(type=types.Type.NUMBER, nullable=True),
                "currency": types.Schema(type=types.Type.STRING, nullable=True),
            },
        ),
        "as_of_text": types.Schema(type=types.Type.STRING, nullable=True,
                                   description="Any visible date/time label, verbatim."),
    },
    required=["holdings"],
)

_EXTRACT_PROMPT = (
    "This is a screenshot of a brokerage/exchange portfolio. Extract ONLY what is "
    "visibly written: each holding's name, a ticker-style symbol guess, quantity and "
    "reported value if shown, plus account totals if shown. If a field is not "
    "readable, set it null. NEVER estimate, infer or compute a number that is not "
    "literally on screen."
)

# symbol_guess -> LMX instrument (demo-set aliases; generic fallback below)
_ALIAS = {
    "BTC": "BTCUSD", "BITCOIN": "BTCUSD", "비트코인": "BTCUSD",
    "ETH": "ETHUSD", "ETHEREUM": "ETHUSD", "이더리움": "ETHUSD",
    "SOL": "SOLUSD", "솔라나": "SOLUSD",
    "XAU": "XAUUSD", "GOLD": "XAUUSD", "금": "XAUUSD",
    "XAG": "XAGUSD", "SILVER": "XAGUSD", "은": "XAGUSD",
    "애플": "AAPL", "테슬라": "TSLA", "엔비디아": "NVDA", "마이크로소프트": "MSFT",
}


def extract_holdings(image_bytes: bytes, mime_type: str = "image/png") -> dict:
    """Step 1 (model): structured read of the screenshot. No computation."""
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=[types.Content(role="user", parts=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            types.Part(text=_EXTRACT_PROMPT),
        ])],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_EXTRACT_SCHEMA,
            http_options=types.HttpOptions(timeout=90_000),
        ),
    )
    out = json.loads(resp.text)
    out["holdings"] = out.get("holdings") or []
    return out


def value_holdings(extract: dict) -> dict:
    """Step 2 (deterministic): price extracted holdings against live LMX quotes.

    All arithmetic happens here, in code. Unmatched or quantity-less holdings are
    reported as unpriced rather than guessed at.
    """
    known = {i["symbol"] for i in mt.list_instruments()["instruments"] if i.get("symbol")}

    rows, unpriced, total = [], [], 0.0
    for h in extract.get("holdings", []):
        guess = str(h.get("symbol_guess") or h.get("name") or "").upper().strip()
        symbol = _ALIAS.get(guess) or (guess if guess in known else None) \
            or (f"{guess}USD" if f"{guess}USD" in known else None)
        qty = h.get("quantity")
        if not symbol or not isinstance(qty, (int, float)) or qty <= 0:
            unpriced.append({"name": h.get("name"), "symbol_guess": guess,
                             "reason": "no LMX instrument match" if not symbol else "no quantity on screen"})
            continue
        q = mt.get_quote(symbol)
        price = q.get("price")
        if not isinstance(price, (int, float)):
            unpriced.append({"name": h.get("name"), "symbol_guess": guess, "reason": "no live quote"})
            continue
        value = round(qty * float(price), 2)
        total = round(total + value, 2)
        rows.append({"name": h.get("name"), "symbol": symbol, "quantity": qty,
                     "live_price": price, "live_value": value,
                     "screenshot_value": h.get("reported_value"),
                     "quote_timestamp": q.get("timestamp")})
    return {"valued": rows, "unpriced": unpriced, "total_live_value": total,
            "currency": "USD", "note": "qty x live LMX quote, computed deterministically in code"}


if __name__ == "__main__":  # checkpoint: extract + value the bundled sample screenshot
    import pathlib
    import sys
    sample = pathlib.Path(__file__).resolve().parent.parent / "service" / "static" / "sample-portfolio.png"
    if not sample.exists():
        print("no sample screenshot at", sample)
        raise SystemExit(1)
    ex = extract_holdings(sample.read_bytes())
    print("extract:", json.dumps(ex, ensure_ascii=False)[:400])
    val = value_holdings(ex)
    print("valuation:", json.dumps(val, ensure_ascii=False)[:400])
    ok = len(ex["holdings"]) >= 2 and len(val["valued"]) >= 2 and val["total_live_value"] > 100
    print("CHECKPOINT:", "GREEN" if ok else "RED")
    raise SystemExit(0 if ok else 1)
