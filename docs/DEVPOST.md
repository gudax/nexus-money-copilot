# Devpost description — NEXUS Money Copilot (Track 1: Build)

> Hard limit 5,000 chars. Keep edits under 4,850 to leave headroom.
> Region: APAC · Entrant: Nexus AI Labs · 2nd submission (Official Rules allow
> "unique and substantially different" multiple entries).

---

## Inspiration

On day 0 of this build, our orchestrator did the exact thing that makes finance chatbots dangerous. An A2A worker crashed — and instead of saying so, the model confidently invented a Bitcoin price of ₩95,845,000 with 2024 timestamps, while the real feed said $61,399, in 2026. Nothing in the model "knew" it was lying.

That incident became the product thesis: **a money copilot is only shippable if honesty is enforced by code, not by prompts.**

## What it does

NEXUS Money Copilot is a personal-finance copilot for the 50+ generation — demoed here in English; the production line serves Korean users on Apps in Toss. Ask it anything about your money — prices, charts, news, your own balance and trade history, or just upload a screenshot of any brokerage app — and **only verified answers come back.**

Every response carries a visible audit stamp: ✓ Verified or ✕ Blocked. The stamp is not decoration; it is the output of a deterministic gate that every answer must pass before it leaves the server.

## How we built it

**ADK multi-agent fleet over real A2A, Gemini on Vertex AI, one Cloud Run container.**

- **markets specialist** (ADK `LlmAgent`, served via `to_a2a()`): grounded in the LMX exchange's live public market API — 82 real instruments (crypto, FX, gold, indices, US stocks), OHLCV candles, news with sentiment, economic calendar. Production trading infrastructure, not a mock.
- **account specialist** (A2A): reads a real demo brokerage account — balance, equity, positions, trade history. READ-ONLY by construction: a GET-only hard allowlist; no order/withdraw/transfer surface exists in the code.
- **orchestrator** (ADK `Agent` + `RemoteA2aAgent` ×2): routes questions to specialists, fails closed when a worker errors.
- **Answer Auditor** — the deterministic seam, no model in the loop:
  1. every money-scale number in the final answer must match the **raw exchange JSON** captured at the worker tool seam *this request* (±3%), or the answer is blocked — model prose is never the truth set, so a worker hallucination can't vouch for itself;
  2. buy/sell recommendations — imperative and soft advisory phrasing alike — and money-movement language (EN+KR tripwire) are blocked regardless of what any model thinks.
- **Vision pipeline** — the model reads, the code computes: Gemini vision extracts structured holdings from a portfolio screenshot (schema forbids invented numbers), then plain Python prices them against live LMX quotes — qty × price never happens inside a model. Both outputs join the session's tool outputs, so the auditor holds the narration to exactly those numbers.

## Challenges we ran into

The day-0 fabrication wasn't hypothetical — it was caused by a real dependency break (current ADK + google-genai versions break A2A-over-Vertex; the worker crashes and an unguarded orchestrator fabricates). We pinned versions, then built the auditor so this failure class can never ship regardless of which dependency breaks next.

The second challenge was arithmetic: a model that values your portfolio is a model doing math, and the auditor (correctly) blocks computed numbers no tool returned. The fix shaped the architecture — deterministic valuation in code, models only narrate pre-verified numbers.

## Accomplishments we're proud of

- Ask "Should I buy now?" — the copilot refuses, by design; the tripwire makes the refusal structural, not stylistic (and it fires in English *and* Korean — a deliberate multilingual defense).
- The fabrication incident from day 0 is now a regression test the auditor must catch (`python fleet/auditor.py`).
- A judge can verify everything in one click: the live demo has a sample-screenshot chip — vision reads it, code prices it live, the audit badge shows how many numbers were checked.

## What we learned

Trust in agent systems is a *seam* problem. Models are excellent readers and narrators and unreliable witnesses; the architecture wins when every number crosses a deterministic checkpoint between the model that read it and the user who acts on it.

## What's next

This fleet is the audited brain for our production consumer line: Nexus AI Labs already operates a Gemini-powered agent for real users on **Apps in Toss — Korea's super-app platform with 30M users**. The verification layer is shared lineage with Sentinel Mesh, our Track 2 entry: the control plane and the consumer fleet that proves it.

## Try it

- Demo video: https://youtu.be/lObQ02WJzBw
- Live demo (Cloud Run): https://money-copilot-675241948019.asia-northeast1.run.app
- Repo: https://github.com/gudax/nexus-money-copilot
- Suggested probes: "How much is Bitcoin right now?" · "Show me my account balance" · the 📷 sample-portfolio chip · and try to make it give investment advice.
