"""
Panel assembly module.
Composites individual shot images into a single labelled storyboard sheet.
"""
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import uuid

from PIL import Image, ImageDraw, ImageFont

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Layout constants
PANEL_W = 512
PANEL_H = 512
LABEL_H = 56        # pixels reserved below each panel for shot labels
PADDING = 20        # padding between panels and sheet edges
COLS = 3            # panels per row on the storyboard sheet
HEADER_H = 80       # height of the top title bar
BG_COLOUR = (245, 245, 250)
PANEL_BG = (220, 220, 230)
LABEL_BG = (30, 30, 50)
LABEL_FG = (240, 240, 240)
TITLE_FG = (20, 20, 40)
BORDER_COLOUR = (180, 180, 200)


def _get_font(size: int = 14) -> ImageFont.ImageFont:
    """Load a truetype font or fall back to default."""
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", size)
        except Exception:
            return ImageFont.load_default()


def _draw_label(draw: ImageDraw.ImageDraw, x: int, y: int, shot: Dict[str, Any]):
    """Render the shot label bar beneath a panel."""
    shot_num = shot.get("shot_number", "?")
    shot_type = shot.get("shot_type", "")
    camera_angle = shot.get("camera_angle", "")
    chars = ", ".join(shot.get("characters", [])) or "—"

    # Background
    draw.rectangle([x, y, x + PANEL_W, y + LABEL_H], fill=LABEL_BG)

    font_sm = _get_font(11)
    font_md = _get_font(13)

    draw.text((x + 6, y + 4), f"SHOT {shot_num}", font=font_md, fill=LABEL_FG)
    draw.text(
        (x + 6, y + 22),
        f"{shot_type.upper()}  ·  {camera_angle.upper()}",
        font=font_sm,
        fill=(180, 200, 220),
    )
    draw.text((x + 6, y + 38), f"CHARS: {chars}", font=font_sm, fill=(160, 180, 200))


class StoryboardAssembler:
    """
    Assembles generated shot images into a labelled storyboard sheet.
    """

    def __init__(self):
        """Initialise the assembler."""
        self.output_dir = settings.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("StoryboardAssembler initialised")

    def assemble(
        self,
        project_id: str,
        title: str,
        shots: List[Dict[str, Any]],
    ) -> str:
        """
        Composite all panels into a single storyboard sheet PNG.

        Args:
            project_id: Project identifier.
            title:       Storyboard title shown in the header.
            shots:       Ordered list of shot dicts, each with ``image_path``.

        Returns:
            Path to the assembled sheet PNG.
        """
        try:
            n = len(shots)
            if n == 0:
                raise ValueError("No shots to assemble")

            rows = (n + COLS - 1) // COLS  # ceiling division

            sheet_w = COLS * (PANEL_W + PADDING) + PADDING
            sheet_h = HEADER_H + rows * (PANEL_H + LABEL_H + PADDING) + PADDING

            sheet = Image.new("RGB", (sheet_w, sheet_h), BG_COLOUR)
            draw = ImageDraw.Draw(sheet)

            # ── Title bar ────────────────────────────────────────────────────
            draw.rectangle([0, 0, sheet_w, HEADER_H], fill=(30, 30, 50))
            font_title = _get_font(22)
            draw.text(
                (PADDING, (HEADER_H - 22) // 2),
                title or "Storyboard",
                font=font_title,
                fill=(240, 240, 255),
            )

            # ── Panels ───────────────────────────────────────────────────────
            for idx, shot in enumerate(shots):
                row = idx // COLS
                col = idx % COLS

                x = PADDING + col * (PANEL_W + PADDING)
                y = HEADER_H + PADDING + row * (PANEL_H + LABEL_H + PADDING)

                # Load panel image
                img_path = shot.get("image_path")
                if img_path and Path(img_path).exists():
                    try:
                        panel_img = Image.open(img_path).convert("RGB").resize(
                            (PANEL_W, PANEL_H), Image.LANCZOS
                        )
                    except Exception:
                        panel_img = self._placeholder_panel(shot)
                else:
                    panel_img = self._placeholder_panel(shot)

                # Border
                draw.rectangle(
                    [x - 2, y - 2, x + PANEL_W + 2, y + PANEL_H + 2],
                    outline=BORDER_COLOUR,
                    width=2,
                )
                sheet.paste(panel_img, (x, y))

                # Label
                _draw_label(draw, x, y + PANEL_H, shot)

            # ── Save ─────────────────────────────────────────────────────────
            project_dir = self.output_dir / project_id
            project_dir.mkdir(parents=True, exist_ok=True)
            dest = project_dir / f"storyboard_{uuid.uuid4().hex[:8]}.png"
            sheet.save(dest, "PNG")
            logger.info(f"Storyboard sheet assembled: {dest}")
            return str(dest)

        except Exception as e:
            logger.error(f"Storyboard assembly failed: {e}")
            raise

    def _placeholder_panel(self, shot: Dict[str, Any]) -> Image.Image:
        """Generate a simple placeholder for a shot whose image isn't ready yet."""
        img = Image.new("RGB", (PANEL_W, PANEL_H), PANEL_BG)
        draw = ImageDraw.Draw(img)
        draw.text(
            (PANEL_W // 2 - 60, PANEL_H // 2 - 10),
            f"SHOT {shot.get('shot_number', '?')}\nGenerating…",
            fill=(100, 100, 120),
            font=_get_font(16),
        )
        return img


def get_assembler() -> StoryboardAssembler:
    """Return a configured StoryboardAssembler instance."""
    return StoryboardAssembler()
