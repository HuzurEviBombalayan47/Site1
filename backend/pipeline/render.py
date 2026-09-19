"""FFmpeg render engine. Builds an MP4 from a timeline (visuals + captions + sfx + audio)."""
import os
import subprocess
import tempfile
import textwrap
import requests
from pathlib import Path

from pipeline.sfx import sfx_path
from pipeline.timeline import FORMATS

FPS = 30

FADE_BY_MODE = {"documentary": 0.25, "normal": 0.14, "fast": 0.06, "shitpost": 0.0}

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
DEJAVU = next((p for p in _FONT_CANDIDATES if os.path.exists(p)), _FONT_CANDIDATES[0])


def _run(cmd: list):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:6])}...\n{proc.stderr[-1500:]}")
    return proc


def download(url: str, dest: Path):
    r = requests.get(url, stream=True, timeout=90)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    return dest


def _zoompan_expr(effect: str, w: int, h: int, nframes: int):
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"
    if effect == "zoom_in":
        return f"z='min(1.001+0.0022*on,1.35)'", center_x, center_y
    if effect == "zoom_out":
        return f"z='max(1.35-0.0022*on,1.0)'", center_x, center_y
    if effect == "pan_right":
        return "z='1.18'", f"'(on/{nframes})*(iw-iw/zoom)'", center_y
    if effect == "pan_left":
        return "z='1.18'", f"'(1-on/{nframes})*(iw-iw/zoom)'", center_y
    if effect == "shake":
        return "z='1.14+0.05*sin(on/1.4)'", center_x, center_y
    # kenburns default (gentle)
    return "z='min(1.0+0.0012*on,1.2)'", center_x, center_y


def _fade_suffix(dur: float, fade: float):
    if fade <= 0 or dur <= fade * 2:
        return ""
    return f",fade=t=in:st=0:d={fade:.2f},fade=t=out:st={dur - fade:.2f}:d={fade:.2f}"


def _text_card(text, w, h, dur, fade, job_dir, idx) -> Path:
    """Animated typography over a moving cinematic gradient (never a plain solid color)."""
    text = (text or "").strip() or "…"
    wrapped = "\n".join(textwrap.wrap(text, width=26)[:4]) or "…"
    txt_path = job_dir / f"txt_{idx:04d}.txt"
    txt_path.write_text(wrapped)
    fs = max(30, int(h / 14))
    seg_out = job_dir / f"seg_{idx:04d}.mp4"
    grad = (f"gradients=s={w}x{h}:c0=0x0c1018:c1=0x243350:x0=0:y0=0:"
            f"x1={w}:y1={h}:speed=0.012:d={dur}")
    vf = (f"format=yuv420p,drawtext=fontfile={DEJAVU}:textfile={txt_path}:fontcolor=0xEAEAEA:"
          f"fontsize={fs}:x=(w-text_w)/2:y=(h-text_h)/2:line_spacing=14:"
          f"shadowcolor=black@0.7:shadowx=3:shadowy=3{_fade_suffix(dur, fade)}")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", grad,
           "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-r", str(FPS), "-an", "-t", f"{dur}", "-vsync", "cfr", str(seg_out)]
    _run(cmd)
    return seg_out


def build_segment(clip: dict, canvas: dict, idx: int, job_dir: Path, mode: str) -> Path:
    w, h = canvas["w"], canvas["h"]
    dur = max(0.4, round(clip["end"] - clip["start"], 3))
    nframes = max(1, int(dur * FPS))
    fade = FADE_BY_MODE.get(mode, 0.15)
    seg_out = job_dir / f"seg_{idx:04d}.mp4"
    common_out = [
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-an", "-t", f"{dur}", "-vsync", "cfr", str(seg_out),
    ]

    vtype = clip.get("visual_type")
    url = clip.get("url")
    local = None
    if url:
        try:
            ext = ".mp4" if (vtype == "video" or url.endswith(".mp4")) else (
                ".gif" if url.endswith(".gif") else ".jpg"
            )
            local = download(url, job_dir / f"asset_{idx:04d}{ext}")
        except Exception:
            local = None

    cover = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"

    if local is None:
        return _text_card(
            clip.get("topic") or clip.get("text") or clip.get("visual_concept"),
            w, h, dur, fade, job_dir, idx,
        )

    if local.suffix == ".mp4":
        vf = f"{cover},fps={FPS}{_fade_suffix(dur, fade)}"
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-stream_loop", "-1", "-i", str(local), "-vf", vf] + common_out
        _run(cmd)
        return seg_out

    if local.suffix == ".gif":
        vf = f"{cover},fps={FPS}{_fade_suffix(dur, fade)}"
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-ignore_loop", "0", "-i", str(local), "-vf", vf] + common_out
        _run(cmd)
        return seg_out

    # image with ken burns / zoompan
    z, x, y = _zoompan_expr(clip.get("effect", "kenburns"), w, h, nframes)
    vf = (
        f"{cover},zoompan={z}:x={x}:y={y}:d=1:fps={FPS}:s={w}x{h}"
        f"{_fade_suffix(dur, fade)}"
    )
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-loop", "1", "-i", str(local), "-vf", vf] + common_out
    try:
        _run(cmd)
    except RuntimeError:
        # fallback: static cover if zoompan fails
        vf = f"{cover},fps={FPS}{_fade_suffix(dur, fade)}"
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-loop", "1", "-i", str(local), "-vf", vf] + common_out
        _run(cmd)
    return seg_out


def concat_segments(seg_paths: list, job_dir: Path) -> Path:
    listfile = job_dir / "concat.txt"
    with open(listfile, "w") as f:
        for p in seg_paths:
            f.write(f"file '{p.name}'\n")
    out = job_dir / "visual.mp4"
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
          "-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(out)])
    return out


def _sec_to_ass(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _hex_to_ass(color: str) -> str:
    c = color.lstrip("#")
    if len(c) != 6:
        return "&H00FFFFFF"
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"&H00{b}{g}{r}".upper()


def build_ass(captions: list, style: dict, canvas: dict, job_dir: Path) -> Path:
    w, h = canvas["w"], canvas["h"]
    align = {"bottom": 2, "center": 5, "top": 8}.get(style.get("position", "bottom"), 2)
    size = int(style.get("size", 54) * (h / 1080.0))
    primary = _hex_to_ass(style.get("color", "#FFFFFF"))
    outline = _hex_to_ass(style.get("outline_color", "#000000"))
    bold = -1 if style.get("bold", True) else 0
    ow = style.get("outline_width", 4)
    margin_v = int(h * 0.08)
    font = style.get("font", "DejaVu Sans")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary},{primary},{outline},&H80000000,{bold},0,0,0,100,100,0,0,1,{ow},1,{align},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    upper = style.get("uppercase", False)
    for cap in captions:
        text = cap["text"].replace("\n", " ").strip()
        if upper:
            text = text.upper()
        text = text.replace("{", "(").replace("}", ")")
        lines.append(
            f"Dialogue: 0,{_sec_to_ass(cap['start'])},{_sec_to_ass(cap['end'])},Default,,0,0,0,,{text}\n"
        )
    out = job_dir / "subs.ass"
    with open(out, "w") as f:
        f.write("".join(lines))
    return out


def build_audio(audio_path: Path, sfx: list, job_dir: Path) -> Path:
    valid = [s for s in sfx if s.get("name") and sfx_path(s["name"]).exists()]
    out = job_dir / "mixed.m4a"
    if not valid:
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
              "-i", str(audio_path), "-c:a", "aac", "-b:a", "192k", str(out)])
        return out
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(audio_path)]
    for s in valid:
        cmd += ["-i", str(sfx_path(s["name"]))]
    parts = []
    labels = ["0:a"]
    for i, s in enumerate(valid):
        ms = int(max(0.0, s["time"]) * 1000)
        vol = float(s.get("volume", 0.9))
        parts.append(f"[{i+1}:a]adelay={ms}|{ms},volume={vol}[s{i}]")
        labels.append(f"s{i}")
    mixchain = "".join(f"[{l}]" for l in labels)
    filtergraph = ";".join(parts) + f";{mixchain}amix=inputs={len(labels)}:duration=first:normalize=0[aout]"
    cmd += ["-filter_complex", filtergraph, "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", str(out)]
    _run(cmd)
    return out


def finalize(visual: Path, audio: Path, ass: Path, captions_enabled: bool, out_path: Path):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(visual), "-i", str(audio)]
    if captions_enabled and ass is not None:
        vf = f"ass={ass.name}"
        cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
    else:
        cmd += ["-c:v", "copy"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", str(out_path)]
    # run in job dir so ass relative path resolves
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(out_path.parent))
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg finalize failed:\n{proc.stderr[-1500:]}")
    return out_path


def render_timeline(job: dict, job_dir: Path, audio_path: Path, progress_cb) -> Path:
    """Full render. progress_cb(pct:int, stage:str)."""
    timeline = job["timeline"]
    canvas = timeline["canvas"]
    visuals = sorted(timeline["visuals"], key=lambda c: c["start"])
    mode = job.get("mode", "normal")

    progress_cb(5, "Görseller indiriliyor...")
    seg_paths = []
    total = len(visuals)
    for i, clip in enumerate(visuals):
        seg = build_segment(clip, canvas, i, job_dir, mode)
        seg_paths.append(seg)
        progress_cb(5 + int(60 * (i + 1) / max(1, total)), "Videonun ritmi oluşturuluyor...")

    progress_cb(70, "Sahneler birleştiriliyor...")
    visual = concat_segments(seg_paths, job_dir)

    progress_cb(80, "Ses efektleri yerleştiriliyor...")
    audio = build_audio(audio_path, timeline.get("sfx", []), job_dir)

    style = job.get("caption_style", {})
    captions_enabled = bool(style.get("enabled", True)) and bool(timeline.get("captions"))
    ass = build_ass(timeline.get("captions", []), style, canvas, job_dir) if captions_enabled else None

    progress_cb(90, "Video hazırlanıyor...")
    out_path = job_dir / "output.mp4"
    finalize(visual, audio, ass, captions_enabled, out_path)
    progress_cb(100, "Tamamlandı")
    return out_path
