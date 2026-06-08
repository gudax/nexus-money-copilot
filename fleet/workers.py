#!/usr/bin/env python3
"""NEXUS Money Copilot fleet — specialist ADK agents served over A2A.

D0 scope: the markets specialist, grounded in the LMX exchange's live public
market API (real production trading infrastructure, credential-free read-only).
"""
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.genai import types

import account_tools as at
import markets_tools as mt

MODEL = Gemini(
    model="gemini-flash-latest",
    retry_options=types.HttpRetryOptions(attempts=5, initial_delay=2.0, max_delay=30.0),
)

markets = LlmAgent(
    name="markets",
    model=MODEL,
    description=(
        "Market-data specialist for the LMX exchange (82 live instruments: crypto, "
        "FX, metals, energy, indices, US stocks). Quotes, OHLCV history for charts, "
        "news with sentiment, economic calendar, funding rates."
    ),
    instruction=(
        "You are the markets specialist in a personal-finance copilot fleet serving "
        "users (many aged 50+). Use your tools for EVERY factual market "
        "answer — never answer prices from memory. Rules:\n"
        "- get_quote for current prices; get_candles when a chart or trend is asked "
        "(default 1h × 48). When returning chart data, include the candle series "
        "as compact JSON under a CHART_DATA: line so the orchestrator can render it.\n"
        "- get_news / get_calendar for 'why is it moving' and 'what's coming' questions.\n"
        "- Answer in clear, plain English — no jargon walls. "
        "State the data timestamp EXACTLY as returned, labeled UTC — never relabel "
        "or convert timezones. You provide information, never investment advice; "
        "do not recommend buying or selling."
    ),
    tools=[mt.list_instruments, mt.get_quote, mt.get_candles, mt.get_news,
           mt.get_calendar, mt.get_funding],
)

account = LlmAgent(
    name="account",
    model=MODEL,
    description=(
        "Account specialist: the user's brokerage account on the LMX platform — "
        "balance, equity, margin, wallets, open positions, recent trade history."
    ),
    instruction=(
        "You are the account specialist in a personal-finance copilot fleet for "
        "users (many aged 50+). Use your tools for EVERY account answer — "
        "never estimate or recall balances. Rules:\n"
        "- get_portfolio for balance/equity/margin; get_trades for history; "
        "get_positions for open exposure; get_wallets for per-currency balances.\n"
        "- Answer in clear, plain English. Quote figures exactly as returned (USDT). "
        "Do not convert currencies.\n"
        "- READ-ONLY: you cannot place, modify or close orders, and must say so if "
        "asked. Information only, never investment advice."
    ),
    tools=[at.get_portfolio, at.get_wallets, at.get_positions, at.get_trades],
)
