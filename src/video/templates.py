from pathlib import Path

import numpy as np
from loguru import logger
from moviepy.editor import (
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoClip,
)
from PIL import Image, ImageDraw, ImageFont

from src.video.palette import (
    CARD_BG,
    CARD_BG_ALPHA,
    CROSSFADE_DURATION,
    FONT_ITALIC,
    FONT_PRIMARY,
    FONT_SECONDARY,
    TEXT_ACCENT,
    TEXT_PRIMARY,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    font_paths = [
        f"/usr/share/fonts/truetype/{name}.ttf",
        f"/usr/local/share/fonts/{name}.ttf",
        f"assets/fonts/{name}.ttf",
    ]
    for p in font_paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    logger.warning("Font '{}' not found — using PIL default", name)
    return ImageFont.load_default()


def _rgba_card_bg(alpha: int = CARD_BG_ALPHA) -> tuple:
    return (CARD_BG[0], CARD_BG[1], CARD_BG[2], alpha)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def make_name_card(name: str, role: str, duration: float = 4.0) -> ImageClip:
    w, h = 600, 90
    img = Image.new("RGBA", (w, h), _rgba_card_bg())
    draw = ImageDraw.Draw(img)

    font_name = _load_font(FONT_PRIMARY, 42)
    font_role = _load_font(FONT_SECONDARY, 26)

    draw.text((20, 8), name, font=font_name, fill=(*TEXT_PRIMARY, 255))
    draw.text((20, 56), role, font=font_role, fill=(*TEXT_ACCENT, 255))

    arr = np.array(img)
    clip = (
        ImageClip(arr, ismask=False)
        .set_duration(duration)
        .fadein(0.3)
        .fadeout(0.3)
        .set_position((60, VIDEO_HEIGHT - 160))
    )
    return clip


def make_location_stamp(location: str, year: str, duration: float) -> ImageClip:
    w, h = 300, 40
    img = Image.new("RGBA", (w, h), _rgba_card_bg())
    draw = ImageDraw.Draw(img)

    font = _load_font(FONT_SECONDARY, 22)
    text = f"{location} · {year}"
    draw.text((10, 8), text, font=font, fill=(*TEXT_PRIMARY, 255))

    arr = np.array(img)
    clip = (
        ImageClip(arr, ismask=False)
        .set_duration(duration)
        .fadein(0.3)
        .fadeout(0.3)
        .set_position((60, VIDEO_HEIGHT - 60))
    )
    return clip


def make_quote_card(quote: str, attribution: str = "", duration: float = 5.0) -> ImageClip:
    w, h = VIDEO_WIDTH, VIDEO_HEIGHT
    overlay_alpha = int(0.90 * 255)
    img = Image.new("RGBA", (w, h), _rgba_card_bg(overlay_alpha))
    draw = ImageDraw.Draw(img)

    font_quote = _load_font(FONT_ITALIC, 52)
    font_attr = _load_font(FONT_SECONDARY, 28)

    max_text_width = 1400
    lines = _wrap_text(quote, font_quote, max_text_width)

    line_heights: list[int] = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_quote)
        line_heights.append(bbox[3] - bbox[1])

    line_spacing = 12
    block_height = sum(line_heights) + line_spacing * (len(lines) - 1)

    attr_h = 0
    if attribution:
        ab = draw.textbbox((0, 0), attribution, font=font_attr)
        attr_h = ab[3] - ab[1]

    line_gap = 24
    total_height = block_height + (line_gap + 2 + line_gap + attr_h if attribution else 0)
    y_start = (h - total_height) // 2

    y = y_start
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font_quote)
        lw = bbox[2] - bbox[0]
        x = (w - lw) // 2
        draw.text((x, y), line, font=font_quote, fill=(*TEXT_PRIMARY, 255))
        y += line_heights[i] + (line_spacing if i < len(lines) - 1 else 0)

    if attribution:
        y += line_gap
        line_x0 = (w - 300) // 2
        line_x1 = (w + 300) // 2
        draw.line([(line_x0, y), (line_x1, y)], fill=(*TEXT_ACCENT, 255), width=1)
        y += line_gap
        ab = draw.textbbox((0, 0), attribution, font=font_attr)
        aw = ab[2] - ab[0]
        draw.text(((w - aw) // 2, y), attribution, font=font_attr, fill=(*TEXT_ACCENT, 255))

    arr = np.array(img)
    clip = (
        ImageClip(arr, ismask=False)
        .set_duration(duration)
        .fadein(0.5)
        .fadeout(0.5)
    )
    return clip


def make_title_card(case_name: str, duration: float = 3.0) -> ImageClip:
    w, h = VIDEO_WIDTH, VIDEO_HEIGHT
    img = Image.new("RGBA", (w, h), (*CARD_BG, 255))
    draw = ImageDraw.Draw(img)

    font = _load_font(FONT_PRIMARY, 80)
    text = case_name.upper()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    tx = (w - tw) // 2
    ty = (h - th) // 2 - 20
    draw.text((tx, ty), text, font=font, fill=(*TEXT_PRIMARY, 255))

    line_y = ty + th + 28
    line_x0 = (w - 400) // 2
    line_x1 = (w + 400) // 2
    draw.line([(line_x0, line_y), (line_x1, line_y)], fill=(*TEXT_ACCENT, 255), width=2)

    arr = np.array(img)
    clip = (
        ImageClip(arr, ismask=False)
        .set_duration(duration)
        .fadein(1.0)
        .fadeout(0.5)
    )
    return clip


def make_timeline_graphic(events: list[dict], duration: float = 6.0) -> ImageClip:
    w, h = VIDEO_WIDTH, 120
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_date = _load_font(FONT_SECONDARY, 20)
    font_label = _load_font(FONT_SECONDARY, 16)

    n = len(events)
    if n == 0:
        arr = np.array(img)
        return ImageClip(arr, ismask=False).set_duration(duration).set_position((0, VIDEO_HEIGHT - 140))

    margin = 120
    step = (w - 2 * margin) // max(n - 1, 1)
    line_y = h // 2

    draw.line([(margin, line_y), (w - margin, line_y)], fill=(*TEXT_ACCENT, 255), width=2)

    dot_r = 8
    for i, event in enumerate(events):
        x = margin + i * step if n > 1 else w // 2
        draw.ellipse(
            [(x - dot_r, line_y - dot_r), (x + dot_r, line_y + dot_r)],
            fill=(*TEXT_ACCENT, 255),
        )

        date_str = event.get("date", "")
        db = draw.textbbox((0, 0), date_str, font=font_date)
        dw = db[2] - db[0]
        draw.text((x - dw // 2, line_y - dot_r - 28), date_str, font=font_date, fill=(*TEXT_PRIMARY, 255))

        label_str = event.get("label", "")
        lb = draw.textbbox((0, 0), label_str, font=font_label)
        lw = lb[2] - lb[0]
        draw.text((x - lw // 2, line_y + dot_r + 6), label_str, font=font_label, fill=(*TEXT_ACCENT, 255))

    arr = np.array(img)
    clip = (
        ImageClip(arr, ismask=False)
        .set_duration(duration)
        .fadein(0.3)
        .fadeout(0.3)
        .set_position((0, VIDEO_HEIGHT - 140))
    )
    return clip


def apply_vignette(clip) -> CompositeVideoClip:
    vignette_strength = 0.4
    h, w = VIDEO_HEIGHT, VIDEO_WIDTH

    y_lin = np.linspace(-1, 1, h)
    x_lin = np.linspace(-1, 1, w)
    xv, yv = np.meshgrid(x_lin, y_lin)
    radius = np.sqrt(xv ** 2 + yv ** 2)
    radius = radius / radius.max()
    mask = radius.astype(np.float32)

    def make_frame(t):
        frame = clip.get_frame(t).astype(np.float32)
        factor = 1.0 - vignette_strength * mask[:, :, np.newaxis]
        return np.clip(frame * factor, 0, 255).astype(np.uint8)

    vignette_clip = VideoClip(make_frame, duration=clip.duration)
    vignette_clip = vignette_clip.set_fps(clip.fps if hasattr(clip, "fps") and clip.fps else 30)
    return CompositeVideoClip([vignette_clip])


def ken_burns(
    image_path: str,
    duration: float,
    zoom_start: float = 1.0,
    zoom_end: float = 1.08,
) -> VideoClip:
    src = Image.open(image_path).convert("RGB")
    src_ratio = src.width / src.height
    target_ratio = VIDEO_WIDTH / VIDEO_HEIGHT

    if src_ratio > target_ratio:
        new_h = VIDEO_HEIGHT
        new_w = int(src_ratio * new_h)
    else:
        new_w = VIDEO_WIDTH
        new_h = int(new_w / src_ratio)

    base = src.resize((new_w, new_h), Image.LANCZOS)
    base_arr = np.array(base)

    def make_frame(t: float) -> np.ndarray:
        progress = t / duration if duration > 0 else 0.0
        zoom = zoom_start + (zoom_end - zoom_start) * progress

        zoomed_w = int(new_w * zoom)
        zoomed_h = int(new_h * zoom)
        zoomed = Image.fromarray(base_arr).resize((zoomed_w, zoomed_h), Image.LANCZOS)

        left = (zoomed_w - VIDEO_WIDTH) // 2
        top = (zoomed_h - VIDEO_HEIGHT) // 2
        cropped = zoomed.crop((left, top, left + VIDEO_WIDTH, top + VIDEO_HEIGHT))
        return np.array(cropped)

    return VideoClip(make_frame, duration=duration).set_fps(30)


def crossfade(clip1, clip2, duration: float = CROSSFADE_DURATION):
    c1 = clip1.crossfadeout(duration)
    c2 = clip2.crossfadein(duration).set_start(clip1.duration - duration)
    return CompositeVideoClip([c1, c2]).set_duration(clip1.duration + clip2.duration - duration)
