#!/usr/bin/env python3
"""Capture film.html into the final demo mp4.

Pipeline: serve repo root -> Playwright records 1920x1080 webm while
film.html?go=1 plays its absolute-deadline timeline -> measure the audio
offset (recording start -> preroll-off) -> assemble vo_full.wav (segments +
pads) -> mux with h264/aac. Output: film/money-copilot-demo.mp4
"""
import json
import pathlib
import shutil
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

FILM = pathlib.Path(__file__).resolve().parent
ROOT = FILM.parent
VO = FILM / "vo"
PORT = 8077


def sh(*args):
    subprocess.run(list(args), check=True)


def build_audio():
    T = json.loads((VO / "timings.json").read_text())
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
       "-i", "anullsrc=r=24000:cl=mono", "-t", str(T["pad"]), str(VO / "pad.wav"))
    lines = []
    for i in range(len(T["durations"])):
        lines.append(f"file 'seg{i+1}.wav'")
        lines.append("file 'pad.wav'")
    (VO / "concat.txt").write_text("\n".join(lines) + "\n")
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
       "-i", str(VO / "concat.txt"), "-c", "copy", str(VO / "vo_full.wav"))
    return T


def capture(total_s):
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT)],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
            ctx = b.new_context(viewport={"width": 1920, "height": 1080},
                                record_video_dir=str(FILM / "_take"),
                                record_video_size={"width": 1920, "height": 1080})
            t_rec0 = time.time()
            pg = ctx.new_page()
            pg.goto(f"http://localhost:{PORT}/film/film.html?go=1")
            pg.wait_for_function("document.getElementById('preroll').classList.contains('off')",
                                 timeout=30000)
            offset = time.time() - t_rec0
            print(f"audio offset: {offset:.2f}s", flush=True)
            pg.wait_for_function("document.title === 'FILM-DONE'",
                                 timeout=(total_s + 40) * 1000)
            pg.wait_for_timeout(1500)
            video = pg.video
            ctx.close()
            raw = pathlib.Path(video.path())
            take = FILM / "take.webm"
            shutil.move(raw, take)
            shutil.rmtree(FILM / "_take", ignore_errors=True)
            b.close()
            return take, offset
    finally:
        server.terminate()


if __name__ == "__main__":
    T = build_audio()
    take, offset = capture(T["total"])
    out = FILM / "money-copilot-demo.mp4"
    sh("ffmpeg", "-y", "-loglevel", "error",
       "-i", str(take),
       "-itsoffset", f"{offset:.2f}", "-i", str(VO / "vo_full.wav"),
       "-map", "0:v", "-map", "1:a",
       "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "160k",
       "-t", f"{offset + T['total'] + 1.5:.2f}",
       str(out))
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    print(f"FINAL: {out} ({float(dur):.1f}s)", "OK under 3:00" if float(dur) < 180 else "!! OVER 3:00")
