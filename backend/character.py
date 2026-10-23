"""
Character reference module.
Stores one visual reference per character (uploaded image, generated from
description, or picked from built-in sketches) and manages the embedding
used for IP-Adapter conditioning across all shots.
"""
import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional, Union, List, Dict, Any

import numpy as np
from PIL import Image

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
# Built-in default sketch library (placeholder images bundled with the app)
# Each entry: { id, name, description, filename }
# Actual PNG files live in static/sketches/
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_SKETCHES: List[Dict[str, str]] = [
    {
        "id": "hero_male",
        "name": "Hero – Male",
        "description": "Young male protagonist with determined expression",
        "filename": "sketch_hero_male.png",
    },
    {
        "id": "hero_female",
        "name": "Hero – Female",
        "description": "Young female protagonist with confident posture",
        "filename": "sketch_hero_female.png",
    },
    {
        "id": "villain",
        "name": "Villain",
        "description": "Menacing figure in dark attire",
        "filename": "sketch_villain.png",
    },
    {
        "id": "elder",
        "name": "Elder / Mentor",
        "description": "Wise older character with calm expression",
        "filename": "sketch_elder.png",
    },
    {
        "id": "child",
        "name": "Child",
        "description": "Young child with curious expression",
        "filename": "sketch_child.png",
    },
    {
        "id": "soldier",
        "name": "Soldier",
        "description": "Military character in uniform",
        "filename": "sketch_soldier.png",
    },
]


class CharacterError(Exception):
    """Custom exception for character-related errors."""
    pass


class CharacterReferenceService:
    """
    Manages character visual references and their embeddings.

    Reference types
    ---------------
    - ``uploaded``  : user supplied an image file
    - ``generated`` : reference synthesised from a text description via SD
    - ``default``   : picked from the built-in sketch library
    """

    def __init__(self):
        """Initialise storage directories."""
        self.characters_dir = settings.upload_dir / "characters"
        self.embeddings_dir = settings.output_dir / "embeddings"
        self.sketches_dir = settings.static_dir / "sketches"

        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self.embeddings_dir.mkdir(parents=True, exist_ok=True)
        self.sketches_dir.mkdir(parents=True, exist_ok=True)

        # Create placeholder sketch PNGs if they don't exist yet
        self._ensure_default_sketches()
        logger.info("CharacterReferenceService initialised")

    # ─────────────────────────────── helpers ─────────────────────────────────

    def _ensure_default_sketches(self):
        """
        Create simple placeholder sketch images for the built-in library.
        These are intentionally minimal solid-colour PNG files so the app runs
        without any extra assets.  Replace them with real artwork for a
        production build.
        """
        PALETTE = {
            "sketch_hero_male.png":   (100, 140, 200),
            "sketch_hero_female.png": (200, 140, 170),
            "sketch_villain.png":     (60,  60,  80),
            "sketch_elder.png":       (180, 160, 130),
            "sketch_child.png":       (220, 200, 100),
            "sketch_soldier.png":     (80,  100, 70),
        }
        for filename, colour in PALETTE.items():
            dest = self.sketches_dir / filename
            if dest.exists():
                continue
            img = Image.new("RGB", (512, 512), colour)
            # Draw a simple silhouette circle (head) as a visual hint
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            # head
            draw.ellipse([156, 80, 356, 280], fill=(230, 200, 170))
            # body
            draw.rectangle([196, 280, 316, 460], fill=(160, 160, 160))
            img.save(dest, "PNG")
        logger.debug("Default sketch PNGs verified / created")

    def _save_reference_image(
        self,
        project_id: str,
        character_id: str,
        image: Image.Image,
    ) -> Path:
        """Persist a PIL Image as the character's reference file."""
        dest_dir = self.characters_dir / project_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{character_id}.png"
        image.save(dest, "PNG")
        return dest

    # ─────────────────────────── public API ──────────────────────────────────

    def save_uploaded_reference(
        self,
        project_id: str,
        character_name: str,
        source_path: Union[str, Path],
    ) -> Dict[str, Any]:
        """
        Store an uploaded image as a character reference.

        Args:
            project_id:      Project this character belongs to.
            character_name:  Display name (e.g. "MAYA").
            source_path:     Path to the uploaded image file.

        Returns:
            Character info dict with ``id``, ``name``, ``reference_type``,
            and ``reference_image_path``.
        """
        character_id = str(uuid.uuid4())
        try:
            img = Image.open(source_path).convert("RGB")
            img = img.resize((512, 512), Image.LANCZOS)
            dest = self._save_reference_image(project_id, character_id, img)

            logger.info(
                f"Saved uploaded reference for '{character_name}' → {dest}"
            )
            return {
                "id": character_id,
                "name": character_name,
                "reference_type": "uploaded",
                "reference_image_path": str(dest),
                "embedding_path": None,
            }
        except Exception as e:
            logger.error(f"Failed to save uploaded reference: {e}")
            raise CharacterError(
                f"Could not save the reference image for '{character_name}'. "
                f"Please make sure the file is a valid image (PNG, JPG, WEBP). "
                f"Details: {e}"
            )

    def save_default_sketch_reference(
        self,
        project_id: str,
        character_name: str,
        sketch_id: str,
    ) -> Dict[str, Any]:
        """
        Use one of the built-in default sketches as a character reference.

        Args:
            project_id:     Project this character belongs to.
            character_name: Display name.
            sketch_id:      One of the IDs in DEFAULT_SKETCHES.

        Returns:
            Character info dict.
        """
        sketch = next(
            (s for s in DEFAULT_SKETCHES if s["id"] == sketch_id), None
        )
        if not sketch:
            raise CharacterError(
                f"Unknown sketch ID '{sketch_id}'. "
                f"Available options: {[s['id'] for s in DEFAULT_SKETCHES]}"
            )

        character_id = str(uuid.uuid4())
        sketch_path = self.sketches_dir / sketch["filename"]

        try:
            img = Image.open(sketch_path).convert("RGB")
            dest = self._save_reference_image(project_id, character_id, img)

            logger.info(
                f"Saved default sketch '{sketch_id}' for '{character_name}'"
            )
            return {
                "id": character_id,
                "name": character_name,
                "reference_type": "default",
                "reference_image_path": str(dest),
                "embedding_path": None,
                "sketch_id": sketch_id,
            }
        except Exception as e:
            logger.error(f"Failed to copy default sketch: {e}")
            raise CharacterError(
                f"Could not load default sketch '{sketch_id}'. Details: {e}"
            )

    def save_description_reference(
        self,
        project_id: str,
        character_name: str,
        description: str,
    ) -> Dict[str, Any]:
        """
        Create a reference from a text description.

        The image generator (imagegen.py) is responsible for the actual
        synthesis; this method stores a *placeholder* and records the
        description so the pipeline can generate the image lazily.

        Args:
            project_id:     Project this character belongs to.
            character_name: Display name.
            description:    Appearance description (style, clothing, age, …).

        Returns:
            Character info dict.  ``reference_image_path`` is None until
            ``update_reference_image`` is called by the image generator.
        """
        character_id = str(uuid.uuid4())
        logger.info(
            f"Registered description-based reference for '{character_name}'"
        )
        return {
            "id": character_id,
            "name": character_name,
            "reference_type": "generated",
            "description": description,
            "reference_image_path": None,
            "embedding_path": None,
        }

    def update_reference_image(
        self,
        project_id: str,
        character_id: str,
        image: Image.Image,
    ) -> str:
        """
        Overwrite the stored reference image (used after generation).

        Args:
            project_id:    Project this character belongs to.
            character_id:  Character UUID.
            image:         Generated PIL Image.

        Returns:
            Path to the saved image as a string.
        """
        dest = self._save_reference_image(project_id, character_id, image)
        logger.info(f"Updated reference image for character {character_id}")
        return str(dest)

    def store_embedding(
        self,
        project_id: str,
        character_id: str,
        embedding: np.ndarray,
    ) -> str:
        """
        Persist a CLIP / IP-Adapter embedding vector for a character.

        Args:
            project_id:    Project this character belongs to.
            character_id:  Character UUID.
            embedding:     Numpy array to persist.

        Returns:
            Path to the saved .npy file as a string.
        """
        dest_dir = self.embeddings_dir / project_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{character_id}.npy"
        np.save(dest, embedding)
        logger.debug(f"Stored embedding for character {character_id} → {dest}")
        return str(dest)

    def load_embedding(
        self,
        embedding_path: str,
    ) -> Optional[np.ndarray]:
        """
        Load a previously stored embedding.

        Args:
            embedding_path: Path returned by ``store_embedding``.

        Returns:
            Numpy array or None if the file does not exist.
        """
        path = Path(embedding_path)
        if not path.exists():
            logger.warning(f"Embedding file not found: {embedding_path}")
            return None
        return np.load(path)

    def load_reference_image(
        self,
        reference_image_path: str,
    ) -> Optional[Image.Image]:
        """
        Load the stored reference image for a character.

        Args:
            reference_image_path: Path stored in the character record.

        Returns:
            PIL Image or None if the file does not exist.
        """
        path = Path(reference_image_path)
        if not path.exists():
            logger.warning(f"Reference image not found: {reference_image_path}")
            return None
        return Image.open(path).convert("RGB")

    def get_default_sketches(self) -> List[Dict[str, str]]:
        """
        Return the built-in default sketch library metadata.

        Returns:
            List of sketch descriptor dicts.
        """
        return DEFAULT_SKETCHES


def get_character_service() -> CharacterReferenceService:
    """Return a configured CharacterReferenceService instance."""
    return CharacterReferenceService()
