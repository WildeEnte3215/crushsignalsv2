"""Offline render diagnostic. Original graphics + local word-synthesized fixture audio.
This is NOT researched airplane content and NOT an ElevenLabs quality demonstration.
"""

import os
import re
import wave
from PIL import Image, ImageDraw, ImageFont
from .schemas import Plan
from .scene_planner import narration, timeline
from .sfx import procedural
from .render import render
from .quality import check
from .utils import atomic, command, save, probe, read, valid_media


def fixture_plan():
    sentences = [
        "Why do airplane windows have tiny holes? This is our production engine test.",
        "Real episodes begin with research. Every explanation needs credible sources and a separate fact check.",
        "The engine compares actual video frames, then chooses footage that fits the explanation.",
        "Narration timestamps control each subtitle. Short shots add movement without losing the subject.",
        "A marker appears only when its target is visible. Sound effects stay subtle.",
        "Finally, a simple diagram connects the steps. The finished file passes technical checks before export.",
    ]
    scenes = []
    for i, text in enumerate(sentences):
        scenes.append(
            {
                "id": "s%02d" % i,
                "narration": text,
                "claim_ids": ["fixture"],
                "visual_goal": "Offline synthetic window illustration",
                "search_queries": ["airplane window"],
                "diagram_nodes": ["RESEARCH", "EXPLAIN", "VERIFY"],
                "prefer_diagram": i == 5,
                "edit": {
                    "motion": [
                        "zoom_in",
                        "pan_right",
                        "punch",
                        "zoom_out",
                        "freeze",
                        "none",
                    ][i],
                    "transition": ["cut", "fade", "cut", "dip_black", "cut", "cut"][i],
                    "overlay": "circle" if i == 4 else "arrow" if i == 2 else "label",
                    "label": [
                        "OFFLINE RENDER TEST",
                        "SOURCES FIRST",
                        "FRAME SELECTION",
                        "WORD TIMING",
                        "VERIFIED TARGET",
                        "HOW IT WORKS",
                    ][i],
                    "target": "small black diagnostic dot",
                    "sfx": "whoosh" if i % 2 == 0 else "click",
                },
            }
        )
    return Plan(
        topic="Offline diagnostic",
        hook=sentences[0],
        title="World in 60 — engine diagnostic",
        description="Original synthetic assets and local test voice. No real API calls.",
        scenes=scenes,
    )


def fixture_voice(text, folder):
    wav = folder / "diagnostic.wav"
    meta = folder / "diagnostic_alignment.json"
    old = read(meta)
    if old and old["text"] == text and valid_media(wav, "audio"):
        return wav, old["alignment"]
    parts, starts, ends, chars = [], [], [], []
    elapsed = 0
    for n, match in enumerate(re.finditer(r"\S+\s*", text)):
        token = match.group()
        word = token.strip()
        src, out = folder / "word.txt", folder / "word.wav"
        atomic(src, re.sub(r"[^A-Za-z0-9 ]", "", word))
        command(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "flite=textfile=word.txt:voice=slt",
                "-af",
                "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,atempo=1.2",
                "-ar",
                24000,
                "-ac",
                1,
                "word.wav",
            ],
            cwd=folder,
        )
        with wave.open(str(out), "rb") as f:
            data = f.readframes(f.getnframes())
        duration = len(data) / 2 / 24000
        for i, char in enumerate(token):
            chars.append(char)
            start = elapsed + duration * min(i, len(word)) / len(word)
            end = elapsed + duration * min(i + 1, len(word)) / len(word)
            starts.append(start)
            ends.append(end)
        parts.append(data + b"\x00\x00" * 720)
        elapsed += duration + 0.03
    # Fixture only: speed-scale known word boundaries to exactly 40 seconds.
    raw = folder / "raw.wav"
    with wave.open(str(raw), "wb") as f:
        f.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        f.writeframes(b"".join(parts))
    speed = elapsed / 40
    command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            raw,
            "-af",
            "atempo=%.8f" % speed,
            "-ar",
            48000,
            wav,
        ]
    )
    alignment = {
        "characters": chars,
        "character_start_times_seconds": [v / speed for v in starts],
        "character_end_times_seconds": [v / speed for v in ends],
    }
    save(
        meta,
        {
            "text": text,
            "alignment": alignment,
            "note": "Known synthesized word clips; intra-word character times interpolated for offline tests only.",
        },
    )
    return wav, alignment


def demo(settings):
    folder = settings.root / "output" / "_demo"
    folder.mkdir(parents=True, exist_ok=True)
    plan = fixture_plan()
    audio, alignment = fixture_voice(narration(plan, settings.brand), folder)
    timing = timeline(
        plan,
        settings.brand,
        settings.video,
        alignment,
        float(probe(audio)["format"]["duration"]),
    )
    selections = {}
    for i, scene in enumerate(plan.scenes):
        if i == 5:
            selections[scene.id] = {"kind": "diagram"}
            continue
        w, h = (960, 540) if i in (1, 3) else (540, 960)
        pic = folder / ("fixture_%d.jpg" % i)
        movie = folder / ("fixture_%d.mp4" % i)
        im = Image.new("RGB", (w, h), "#294054")
        d = ImageDraw.Draw(im)
        d.rounded_rectangle(
            (w * 0.19, h * 0.12, w * 0.81, h * 0.83),
            radius=int(w * 0.2),
            fill="#BED7E7",
            outline="#EFF5F9",
            width=18,
        )
        d.rounded_rectangle(
            (w * 0.27, h * 0.20, w * 0.73, h * 0.75),
            radius=int(w * 0.16),
            fill="#73A1BD",
        )
        d.ellipse((w * 0.46, h * 0.55, w * 0.50, h * 0.59), fill="#0B1C30")
        font = ImageFont.truetype(str(settings.font), max(12, int(w * 0.026)))
        d.text(
            (w * 0.08, h * 0.89),
            "SYNTHETIC ASSET / OFFLINE TEST",
            font=font,
            fill="#FFFFFF",
        )
        im.save(pic)
        if not valid_media(movie, "video"):
            command(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-loop",
                    1,
                    "-i",
                    pic,
                    "-t",
                    2.1,
                    "-r",
                    30,
                    "-c:v",
                    "libx264",
                    "-threads",
                    1,
                    "-pix_fmt",
                    "yuv420p",
                    movie,
                ]
            )
        selections[scene.id] = {
            "kind": "stock",
            "path": str(movie),
            "frame": str(pic),
            "offset": 0.3,
            "assessment": {
                "crop": "contain" if i == 1 else "focus",
                "focus_x": 0.48,
                "focus_y": 0.5,
                "target_visible": True,
                "target_confidence": 1,
                "target_x": 0.48,
                "target_y": 0.57,
                "target_radius": 0.045,
            },
        }
    cues = []
    for i, start in enumerate([0.1, 10, 22, 33]):
        p = folder / ("sound_%d.wav" % i)
        procedural(p, "whoosh" if i % 2 == 0 else "pop")
        cues.append(
            {"start": start, "path": str(p), "origin": "Original procedural diagnostic"}
        )
    save(folder / "plan.json", plan.model_dump())
    save(folder / "timeline.json", timing)
    candidate = render(settings, plan, timing, selections, audio, cues, folder)
    check(settings, candidate, timing, folder)
    final = folder / "final.mp4"
    if candidate != final:
        os.replace(candidate, final)
    return final
