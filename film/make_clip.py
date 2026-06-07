#!/usr/bin/env python3
"""Record the live-demo clips against the LIVE Cloud Run service.

Three takes, all real (no mocks, no edits to the answers):
  A. price question -> markets specialist -> verified stamp
     balance question -> account specialist -> verified stamp
  B. sample portfolio screenshot -> vision extract -> code valuation -> verified
  C. "should I buy?" -> structural refusal

Raw takes are slow (model latency), so each is speed-adjusted at mux time to fit
its scene window. Output: film/assets/clip-{a,b,c}.webm + clip-meta.json.
"""
import json
import pathlib
import shutil
import subprocess

from playwright.sync_api import sync_playwright

URL = "https://money-copilot-675241948019.asia-northeast1.run.app"
OUT = pathlib.Path(__file__).resolve().parent / "assets"
SIZE = {"width": 1660, "height": 900}

# (clip name, [questions], use_sample_chip, target seconds after speedup)
TAKES = [
    ("a", ["비트코인 지금 얼마야?", "내 계좌 잔고 알려줘"], False, 19.0),
    ("b", [], True, 21.0),
    ("c", ["비트코인 지금 사야 돼?"], False, 11.0),
]


def wait_answer(pg, n):
    pg.wait_for_function(
        f"document.querySelectorAll('.vbadge').length >= {n} && !document.getElementById('go').disabled",
        timeout=120_000)
    badge = pg.text_content(".turn .vbadge").strip()
    print("  badge:", badge, flush=True)
    assert "검증됨" in badge, f"clip take broken: {badge}"


def record(p, name, questions, sample, target):
    b = p.chromium.launch()
    ctx = b.new_context(viewport=SIZE, record_video_dir=str(OUT / "_clipraw"),
                        record_video_size=SIZE)
    pg = ctx.new_page()
    pg.goto(URL, wait_until="networkidle")
    pg.wait_for_timeout(1500)
    n = 0
    if sample:
        pg.click("#sample-chip")
        n += 1
        wait_answer(pg, n)
        pg.wait_for_timeout(3200)  # linger on the table + badge
    for q in questions:
        pg.fill("#q", "")
        pg.click("#q")
        pg.type("#q", q, delay=30)
        pg.wait_for_timeout(350)
        pg.click("#go")
        n += 1
        wait_answer(pg, n)
        pg.wait_for_timeout(2600)
    pg.wait_for_timeout(900)
    video = pg.video
    ctx.close()
    raw = pathlib.Path(video.path())
    b.close()

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(raw)],
        capture_output=True, text=True).stdout.strip())
    speed = max(1.0, dur / target)
    dest = OUT / f"clip-{name}.webm"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                    "-vf", f"setpts=PTS/{speed:.3f}", "-an",
                    "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", str(dest)], check=True)
    final = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dest)],
        capture_output=True, text=True).stdout.strip())
    print(f"clip-{name}: raw {dur:.1f}s -> x{speed:.2f} -> {final:.1f}s", flush=True)
    shutil.rmtree(OUT / "_clipraw", ignore_errors=True)
    return {"raw_s": round(dur, 1), "speed": round(speed, 2), "final_s": round(final, 1)}


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    meta = {}
    with sync_playwright() as p:
        for name, qs, sample, target in TAKES:
            print(f"take {name}:", flush=True)
            meta[name] = record(p, name, qs, sample, target)
    (OUT / "clip-meta.json").write_text(json.dumps(meta, indent=1))
    print("all clips:", json.dumps(meta))
