#!/usr/bin/env python3
"""NEXUS Money Copilot orchestrator — delegates to specialists over real A2A.

D0 checkpoint runner: asks a market question in Korean, expects the answer to be
produced via the markets worker's LMX tools (price + chart series), not from the
model's memory.
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from workers import MODEL


def remote(name, port):
    return RemoteA2aAgent(
        name=name,
        description=f"Remote {name} specialist reachable over the A2A protocol.",
        agent_card=f"http://127.0.0.1:{port}{AGENT_CARD_WELL_KNOWN_PATH}",
    )


orchestrator = Agent(
    name="copilot",
    model=MODEL,
    description="NEXUS Money Copilot — personal-finance copilot orchestrator.",
    instruction=(
        "You are NEXUS Money Copilot (넥서스 머니 코파일럿), a warm, plain-spoken "
        "personal-finance copilot for Korean users, many aged 50+.\n"
        "- For ANY market fact (price, trend, chart, news, calendar) delegate to the "
        "`markets` specialist — never answer market facts yourself.\n"
        "- Answer in Korean unless asked otherwise. Keep sentences short.\n"
        "- If the specialist returned a CHART_DATA: line, preserve it verbatim at the "
        "end of your answer (the UI renders it as a chart).\n"
        "- FAIL CLOSED: if the specialist errors or returns nothing, say the data is "
        "temporarily unavailable. NEVER invent a price, NEVER convert currencies "
        "yourself, NEVER fabricate CHART_DATA or timestamps. An honest 'unavailable' "
        "beats a confident guess — your answers are audited against the live feed.\n"
        "- Information only — never recommend buying or selling; say so if asked."
    ),
    tools=[AgentTool(agent=remote("markets", 8101))],
)


async def main(question):
    runner = InMemoryRunner(agent=orchestrator)
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id="checkpoint")
    out = []
    async for ev in runner.run_async(
            user_id="checkpoint", session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=question)])):
        if ev.content and ev.content.parts:
            for p in ev.content.parts:
                if p.text:
                    out.append(p.text)
    answer = "\n".join(out)
    print(answer)
    ok = any(tok in answer for tok in ("CHART_DATA", "₩", "$", "달러", "61", "6만", "BTC", "비트코인"))
    print("\nCHECKPOINT:", "GREEN" if ok and len(answer) > 40 else "RED")
    return 0 if ok else 1


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "비트코인 지금 얼마야? 최근 하루 흐름도 차트로 보여줘."
    raise SystemExit(asyncio.run(main(q)))
