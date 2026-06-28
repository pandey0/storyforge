from __future__ import annotations

import io
import os
from pathlib import Path

from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from src.db.models import Case, Video
from src.db.session import get_session
from src.pipeline.state import CaseState
from src.video.palette import CARD_BG, TEXT_ACCENT, TEXT_PRIMARY


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    # Devanagari-capable fonts first, then Latin fallbacks
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Bold.otf",
        "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _load_font_regular(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.otf",
        "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


class ThumbnailAgent:
    W = 1280
    H = 720

    def run(self, state: CaseState) -> CaseState:
        with get_session() as session:
            case = session.query(Case).filter(Case.slug == state.slug).first()
            if case is None:
                raise ValueError(f"Case not found: {state.slug}")

            logger.info(f"ThumbnailAgent: generating thumbnail for {state.slug}")

            image_bytes = self._generate_image(
                case_name=case.name,
                victim_name=case.subject_name or "",
                case_type=case.extra.get("case_type") or "",
            )

            title_text = case.name
            pil_image = self._add_text_overlay(image_bytes, title_text, case.name)

            thumb_path = self._save(pil_image, state.slug)

            video = (
                session.query(Video)
                .filter(Video.case_id == case.id)
                .order_by(Video.created_at.desc())
                .first()
            )
            if video is not None:
                video.thumbnail_path = thumb_path

            case.status = "ready"
            state.thumbnail_path = thumb_path
            state.status = "ready"

        logger.success(f"ThumbnailAgent: thumbnail saved → {thumb_path}")
        return state

    def _build_prompt(self, case_name: str, victim_name: str) -> str:
        return (
            f"A cinematic documentary thumbnail image for a Hindi true crime video about the {case_name} in India. "
            "Dark, moody, journalistic photography style. Location: India — streets, courts, or landmarks. "
            "Warm amber and shadow tones. No text. No people's faces. "
            "Style: Netflix documentary poster, desaturated warm tones, high contrast lighting. "
            "Evocative of justice, investigation, and human drama. NOT sensational or gore. NOT horror."
        )

    def _generate_image(self, case_name: str, victim_name: str, case_type: str) -> bytes:
        from src.providers.image_gen import TaskType, generate_image

        prompt = self._build_prompt(case_name, victim_name)
        try:
            return generate_image(prompt, task=TaskType.THUMBNAIL)
        except Exception as exc:
            logger.warning(f"Image generation failed ({exc}) — using fallback image")
            return self._fallback_image_bytes()

    def _fallback_image_bytes(self) -> bytes:
        img = Image.new("RGB", (self.W, self.H), color=CARD_BG)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()

    def _add_text_overlay(self, image_bytes: bytes, title_text: str, case_name: str) -> Image.Image:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = img.resize((self.W, self.H), Image.LANCZOS)

        overlay = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)

        gradient_top = int(self.H * 0.60)
        for y in range(gradient_top, self.H):
            alpha = int(180 * (y - gradient_top) / (self.H - gradient_top))
            draw_ov.rectangle([(0, y), (self.W, y)], fill=(0, 0, 0, alpha))

        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        display_title = title_text[:40]
        if len(title_text) <= 30:
            display_title = display_title.upper()

        font_title = _load_font(72)
        font_case = _load_font_regular(38)

        shadow_offset = 3
        draw.text(
            (self.W // 2 + shadow_offset, 520 + shadow_offset),
            display_title,
            font=font_title,
            fill=(0, 0, 0),
            anchor="mm",
        )
        draw.text(
            (self.W // 2, 520),
            display_title,
            font=font_title,
            fill=TEXT_PRIMARY,
            anchor="mm",
        )

        draw.text(
            (self.W // 2, 610),
            case_name[:60],
            font=font_case,
            fill=TEXT_ACCENT,
            anchor="mm",
        )

        return img

    def _save(self, image: Image.Image, slug: str) -> str:
        out_dir = Path(f"data/cases/{slug}/output")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "thumbnail.jpg"
        image.save(str(out_path), format="JPEG", quality=95)
        return str(out_path)
