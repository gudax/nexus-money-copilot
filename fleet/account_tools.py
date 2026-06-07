#!/usr/bin/env python3
"""Account agent tool belt — LMX demo account, READ-ONLY.

Auth: one POST /api/auth/login (demo credentials from env, never in code), then
GET-only against a hard allowlist. This talks to a live exchange — there is
deliberately no order/withdrawal/transfer surface in this module, and no code
path can construct one.
"""
import os
import time

import httpx

import truth_log

BASE = "https://api.lmx.mx"
_client = httpx.Client(base_url=BASE, timeout=httpx.Timeout(8.0))
_tok = {"v": None, "t": 0.0}

_ALLOW = ("/api/account/portfolio", "/api/account/wallets", "/api/trading/positions",
          "/api/trading/trades", "/api/account/analytics/equity")


def _token():
    if _tok["v"] and time.time() - _tok["t"] < 600:
        return _tok["v"]
    email = os.environ["LMX_DEMO_EMAIL"]
    password = os.environ["LMX_DEMO_PASSWORD"]
    r = _client.post("/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    _tok["v"] = r.json()["token"]
    _tok["t"] = time.time()
    return _tok["v"]


def _get(path: str, params: dict | None = None):
    assert path.startswith(_ALLOW), f"endpoint not in allowlist: {path}"
    r = _client.get(path, params=params or {}, headers={"Authorization": f"Bearer {_token()}"})
    r.raise_for_status()
    data = r.json()
    truth_log.record(f"account:{path}", data)  # raw account JSON -> auditor truth
    return data


def get_portfolio() -> dict:
    """Account snapshot: balance, equity, free/used margin, unrealized P&L (USDT)."""
    p = _get("/api/account/portfolio")
    return {k: float(v) for k, v in p.items() if v is not None}


def get_wallets() -> dict:
    """Wallet balances per currency."""
    w = _get("/api/account/wallets").get("wallets", [])
    return {"wallets": [{"currency": x.get("currency"), "balance": float(x.get("balance", 0)),
                         "locked": float(x.get("locked", 0))} for x in w]}


def get_positions() -> dict:
    """Open positions: symbol, side, qty, entry, unrealized P&L."""
    rows = _get("/api/trading/positions").get("positions", [])
    return {"count": len(rows), "positions": [
        {"symbol": p.get("symbol"), "side": p.get("side"), "qty": p.get("qty"),
         "entry_price": p.get("entry_price"), "unrealized_pnl": p.get("unrealized_pnl")}
        for p in rows]}


def get_trades(limit: int = 10) -> dict:
    """Recent closed trades, newest first: symbol, side, qty, price, realized P&L, time."""
    rows = _get("/api/trading/trades").get("trades", [])
    return {"count": len(rows), "trades": [
        {"symbol": t.get("symbol"), "side": t.get("side"), "qty": t.get("qty"),
         "price": t.get("price"), "pnl": t.get("pnl") or t.get("realized_pnl"),
         "time": t.get("created_at") or t.get("closed_at")}
        for t in rows[:min(int(limit), 30)]]}


if __name__ == "__main__":  # smoke checkpoint (needs LMX_DEMO_EMAIL/PASSWORD env)
    import json
    p = get_portfolio()
    print("portfolio:", json.dumps(p))
    t = get_trades(3)
    print("trades:", t["count"], json.dumps(t["trades"][:2], ensure_ascii=False)[:200])
    ok = p.get("balance", 0) > 0 and t["count"] > 0
    print("CHECKPOINT:", "GREEN" if ok else "RED")
    raise SystemExit(0 if ok else 1)
