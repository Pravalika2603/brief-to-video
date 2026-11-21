"""Rendering: Pillow draws each scene as a 1080x1920 frame; FFmpeg assembles the MP4."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

from .models import Script

W, H, FPS, FADE = 1080, 1920, 30, 0.3
_FONT_CANDIDATES = [
    os.getenv("B2V_FONT", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover
        raise RuntimeError("ffmpeg not found. Install it or `pip install imageio-ffmpeg`.") from e


def _font(size: int) -> ImageFont.ImageFont:
    for p in _FONT_CANDIDATES:
        if p and Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def brand_colors(brand: str) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """Stable, brand-derived gradient so each client gets a consistent look."""
    h = hashlib.sha256(brand.encode()).digest()
    top = (20 + h[0] % 60, 20 + h[1] % 60, 40 + h[2] % 80)
    bottom = (min(top[0] + 90, 255), min(top[1] + 60, 255), min(top[2] + 110, 255))
    return top, bottom


def _gradient(top, bottom) -> Image.Image:
    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        px.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> List[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


def render_frame(text: str, brand: str, index: int, total: int, is_hook: bool, path: Path) -> None:
    img = _gradient(*brand_colors(brand))
    d = ImageDraw.Draw(img)
    font = _font(110 if is_hook else 84)
    lines = _wrap(d, text, font, W - 160)
    line_h = font.size + 24
    y = (H - line_h * len(lines)) // 2
    for line in lines:
        w = d.textlength(line, font=font)
        d.text(((W - w) / 2 + 3, y + 3), line, font=font, fill=(0, 0, 0))   # shadow
        d.text(((W - w) / 2, y), line, font=font, fill=(255, 255, 255))
        y += line_h
    tag = _font(46)
    d.text((80, H - 170), brand.upper(), font=tag, fill=(255, 255, 255))
    for i in range(total):  # progress dots
        x = W - 80 - (total - i) * 36
        d.ellipse([x, H - 160, x + 20, H - 140], fill=(255, 255, 255) if i <= index else (150, 150, 170))
    img.save(path)


def render_video(script: Script, brand: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    texts, durs = script.scene_texts(), script.durations()
    n = len(texts)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [ffmpeg_bin(), "-y", "-loglevel", "error"]
        for i, (t, dur) in enumerate(zip(texts, durs)):
            frame = Path(tmp) / f"scene{i}.png"
            render_frame(t, brand, i, n, i == 0, frame)
            cmd += ["-loop", "1", "-t", f"{dur}", "-i", str(frame)]
        cmd += ["-f", "lavfi", "-t", f"{sum(durs)}", "-i", "anullsrc=r=44100:cl=stereo"]  # silent audio track
        chains = []
        for i, dur in enumerate(durs):
            chains.append(f"[{i}:v]fade=t=in:st=0:d={FADE},fade=t=out:st={max(dur - FADE, 0)}:d={FADE},"
                          f"setsar=1,format=yuv420p[v{i}]")
        concat = "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
        cmd += ["-filter_complex", ";".join(chains + [concat]), "-map", "[v]", "-map", f"{n}:a",
                "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-shortest",
                "-movflags", "+faststart", str(out_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {proc.stderr[-500:]}")
    return out_path
