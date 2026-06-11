#!/usr/bin/env python3
"""Generate the demo voiceover with Gemini TTS (the VO itself is Google-stack).

Outputs film/vo/seg{N}.wav + film/vo/timings.json {durations, scene starts}.
Scene N runs for VO duration + PAD seconds; film.html consumes the same timings,
so audio and visuals share one deterministic timeline.

Key: GOOGLE_API_KEY env, or auto-loaded from ~/.config/tossnexus (free tier —
3 RPM, so 429 backoff is built in).
"""
import json
import os
import pathlib
import subprocess
import sys
import wave

from google import genai
from google.genai import types

OUT = pathlib.Path(__file__).resolve().parent / "vo"
PAD = 1.6  # breathing room after each VO segment, seconds

STYLE = ("Narrate in a confident, measured, technical product-demo tone, "
         "medium pace, no theatrics: ")

SEGMENTS = [
    # S1 — title
    "NEXUS Money Copilot — a personal-finance copilot for Korea's fifty-plus "
    "generation, built on one promise: ask anything about your money, and only "
    "verified answers come back.",
    # S2 — the day-0 incident
    "On day zero of this build, an A2A worker crashed — and our orchestrator "
    "confidently invented a Bitcoin price. Wrong currency, wrong year. The real "
    "feed, that same second: sixty-one thousand dollars. Nothing in the model "
    "knew it was lying. That incident became the architecture.",
    # S3 — architecture, fast
    "Here is the whole system. A question hits an ADK orchestrator on Cloud "
    "Run — Gemini on Vertex AI — and routes over real A2A, live agent cards, "
    "to three specialists: markets, a real exchange's production API; account, "
    "a real brokerage account, read-only by construction; and vision, where "
    "the model reads and the code computes. Before any answer ships, a "
    "deterministic auditor — no model in the loop — checks every money claim "
    "against the tools' actual returns, and tripwires advice language. "
    "Pass: it ships, stamped. Fail: it never reaches the user.",
    # S4 — live clip A
    "Live on Cloud Run. A price question routes to the markets specialist; a "
    "balance question routes to the account specialist. And every number is a "
    "receipt — tap it, and the answer opens the exact exchange field that proves "
    "it: the source, the field, the matched value, pulled straight from the live "
    "feed. Verification you can open, not a badge you have to trust. The audit "
    "stamp rides on every card, and nothing on screen is a number the tools "
    "did not actually return.",
    # S5 — vision clip B
    "Now the part most copilots get wrong. Upload a screenshot of any "
    "brokerage app. Gemini vision is trusted only to read — structured "
    "extraction, no invented numbers. Then plain Python prices the holdings "
    "against live quotes — multiplication never happens inside a model. The "
    "final narration is audited against exactly those numbers.",
    # S6 — refusal + regression test
    "Ask it whether to buy — it refuses. And the refusal is structural, not "
    "stylistic: a deterministic tripwire blocks recommendation language, in "
    "English and Korean, no matter what any model thinks. The day-zero "
    "fabrication is now a regression test — caught on every run.",
    # S7 — close
    "The same brain is headed for our production line — real users on Apps in "
    "Toss, a thirty-million-user platform. NEXUS Money Copilot: ask anything "
    "about your money. Only verified answers come back.",
]


def synth(client, text, path):
    import re
    import time as _time
    from google.genai import errors
    for attempt in range(5):
        try:
            return _synth_once(client, text, path)
        except errors.ClientError as e:
            if getattr(e, "code", None) != 429 or attempt == 4:
                raise
            m = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e), re.I)
            _time.sleep(float(m.group(1)) + 2 if m else 40)


def _synth_once(client, text, path):
    r = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=STYLE + text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon"))),
        ),
    )
    pcm = r.candidates[0].content.parts[0].inline_data.data
    raw = path.with_suffix(".pcm")
    raw.write_bytes(pcm)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar",
                    "24000", "-ac", "1", "-i", str(raw), str(path)], check=True)
    raw.unlink()
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def _api_key():
    if os.environ.get("GOOGLE_API_KEY"):
        return os.environ["GOOGLE_API_KEY"]
    p = pathlib.Path.home() / ".config/tossnexus/gemini-api-key-create.json"
    return json.load(open(p))["response"]["keyString"]


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    client = genai.Client(api_key=_api_key())
    durations, starts, t = [], [], 0.0
    for i, text in enumerate(SEGMENTS, 1):
        p = OUT / f"seg{i}.wav"
        d = synth(client, text, p)
        durations.append(round(d, 3))
        starts.append(round(t, 3))
        t += d + PAD
        print(f"seg{i}: {d:.2f}s (scene starts at {starts[-1]:.2f}s)", flush=True)
    total = round(t, 3)
    (OUT / "timings.json").write_text(json.dumps(
        {"pad": PAD, "durations": durations, "starts": starts, "total": total}, indent=1))
    print(f"total timeline: {total:.1f}s", "(OK, under 180s)" if total < 180 else "(!! OVER 3:00)")
    sys.exit(0 if total < 180 else 1)
