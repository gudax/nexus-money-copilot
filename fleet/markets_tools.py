#!/usr/bin/env python3
"""Markets agent tool belt — LMX exchange public market API (read-only).

Every tool is a GET against api.lmx.mx's public, credential-free market surface
(82 instruments: crypto via Binance USD-M, FX/metals/energy/indices/US stocks via
institutional feed). HARD ALLOWLIST: only the endpoints below, only GET — this is
a live exchange API, so this module is the single place network access is
defined. No auth header exists in this file.
"""
import httpx

import truth_log

BASE = "https://api.lmx.mx"
_TIMEOUT = httpx.Timeout(8.0)
_client = httpx.Client(base_url=BASE, timeout=_TIMEOUT, headers={"user-agent": "nexus-money-copilot/0.1 (+hackathon demo)"})

_ALLOW = ("/api/market/instruments", "/api/market/candles/", "/api/market/news",
          "/api/market/calendar", "/api/market/financing/", "/api/status")


def _get(path: str, params: dict | None = None):
    assert path.startswith(_ALLOW), f"endpoint not in allowlist: {path}"
    r = _client.get(path, params=params or {})
    r.raise_for_status()
    data = r.json()
    truth_log.record(f"markets:{path}", data)  # raw exchange JSON -> auditor truth
    return data


def _candles(symbol: str, tf: str) -> list:
    """Chronologically ascending OHLCV rows with float fields (API returns newest-first strings)."""
    data = _get(f"/api/market/candles/{symbol.upper()}", {"tf": tf})
    rows = data.get("candles", []) if isinstance(data, dict) else data
    rows = list(reversed(rows))  # API is newest-first
    for c in rows:
        for k in ("open", "high", "low", "close", "volume"):
            try: c[k] = float(c[k])
            except (TypeError, ValueError): pass
    return rows


def list_instruments(category: str = "") -> dict:
    """List tradable instruments on the LMX exchange.

    Args:
        category: optional filter, e.g. 'crypto', 'forex', 'metals', 'indices', 'stocks'.
    Returns dict with `instruments`: [{symbol, name, category, leverage_max}].
    """
    data = _get("/api/market/instruments")
    rows = data.get("instruments", []) if isinstance(data, dict) else data
    out = []
    for i in rows:
        if category and category.lower() not in str(i.get("type", "")).lower():
            continue
        out.append({"symbol": i.get("symbol"), "name": i.get("name"),
                    "type": i.get("type"), "max_leverage": i.get("max_leverage")})
    return {"count": len(out), "instruments": out[:90]}


def get_quote(symbol: str) -> dict:
    """Latest price for one symbol (e.g. BTCUSD, ETHUSD, XAUUSD, NAS100).

    Returns the most recent 1-minute candle: open/high/low/close/volume + timestamp.
    """
    candles = _candles(symbol, "1m")
    if not candles:
        return {"symbol": symbol.upper(), "error": "no data — check symbol via list_instruments"}
    last = candles[-1]
    return {"symbol": symbol.upper(), "price": last.get("close"), "open": last.get("open"),
            "high": last.get("high"), "low": last.get("low"),
            "volume": last.get("volume"), "timestamp": last.get("timestamp")}


def get_candles(symbol: str, timeframe: str = "1h", limit: int = 48) -> dict:
    """OHLCV history for charting. timeframe: 1m|5m|15m|30m|1h|4h|1d. limit<=200."""
    rows = _candles(symbol, timeframe)[-min(int(limit), 200):]
    return {"symbol": symbol.upper(), "timeframe": timeframe, "count": len(rows),
            "candles": [{"t": c.get("timestamp"), "o": c.get("open"), "h": c.get("high"),
                         "l": c.get("low"), "c": c.get("close")} for c in rows]}


def get_news(limit: int = 8) -> dict:
    """Latest market news with sentiment scores (~8 min freshness)."""
    rows = _get("/api/market/news")
    rows = rows.get("articles", []) if isinstance(rows, dict) else rows
    return {"news": [{"title": n.get("title"), "sentiment": n.get("sentiment"),
                      "symbols": n.get("symbols"), "summary": (n.get("summary") or "")[:200]}
                     for n in rows[:min(int(limit), 20)]]}


def get_calendar(limit: int = 10) -> dict:
    """Upcoming economic-calendar events (impact, consensus, previous)."""
    rows = _get("/api/market/calendar")
    rows = rows if isinstance(rows, list) else rows.get("events", [])
    return {"events": [{"title": e.get("title"), "country": e.get("country"),
                        "impact": e.get("impact"), "scheduled_at": e.get("scheduled_at"),
                        "consensus": e.get("consensus"), "previous": e.get("previous")}
                       for e in rows[:min(int(limit), 25)]]}


def get_funding(symbol: str) -> dict:
    """Swap/funding rates for one symbol (8h funding for crypto, swap for TradFi)."""
    return {"symbol": symbol.upper(), "financing": _get(f"/api/market/financing/{symbol.upper()}")}


if __name__ == "__main__":  # smoke checkpoint
    import json
    ins = list_instruments("crypto")
    print("instruments(crypto):", ins["count"])
    q = get_quote("BTCUSD")
    print("BTCUSD quote:", json.dumps(q))
    c = get_candles("BTCUSD", "1h", 5)
    print("candles:", c["count"], "last close:", c["candles"][-1]["c"] if c["candles"] else None)
    n = get_news(3)
    print("news:", [x["title"][:40] for x in n["news"]])
    cal = get_calendar(3)
    print("calendar:", [x["title"][:30] for x in cal["events"]])
    ok = ins["count"] > 0 and q.get("price") and c["count"] > 0
    print("CHECKPOINT:", "GREEN" if ok else "RED")
    raise SystemExit(0 if ok else 1)
