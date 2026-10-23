"""
Consistency evaluation module using OpenCLIP.

Measures how visually consistent a character appears across multiple panels
by computing embedding similarity scores.

All heavy imports (torch, open_clip) are deferred so the app starts even when
these packages are not installed — a clear error is raised only when evaluation
is attempted.
"""
import logging
from typing import List, Dict, Any, Optional

import numpy as np
from PIL import Image

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ConsistencyError(Exception):
    """Custom exception for consistency evaluation errors."""
    pass


def _require_torch():
    try:
        import torch
        return torch
    except ImportError:
        raise ConsistencyError(
            "PyTorch is not installed. Run: pip install torch\n"
            "Consistency scoring will be unavailable until then."
        )


def _require_open_clip():
    try:
        import open_clip
        return open_clip
    except ImportError:
        raise ConsistencyError(
            "open-clip-torch is not installed. Run: pip install open-clip-torch\n"
            "Consistency scoring will be unavailable until then."
        )


class ConsistencyEvaluator:
    """
    Evaluates character consistency across storyboard panels using OpenCLIP.
    Models are loaded lazily on first use.
    """

    def __init__(self, model_name: str = "ViT-B-32", pretrained: str = "openai"):
        """
        Store config; actual model loading is deferred to first use.

        Args:
            model_name: OpenCLIP model architecture.
            pretrained: Pretrained checkpoint name.
        """
        self.model_name = model_name
        self.pretrained = pretrained
        self._model = None
        self._preprocess = None
        self._device: Optional[str] = None
        self._loaded = False

    def _ensure_loaded(self):
        """Load OpenCLIP model on first call."""
        if self._loaded:
            return
        torch = _require_torch()
        open_clip = _require_open_clip()

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading OpenCLIP {self.model_name} on {self._device}")

        try:
            self._model, _, self._preprocess = open_clip.create_model_and_transforms(
                self.model_name,
                pretrained=self.pretrained,
                device=self._device,
            )
            self._model.eval()
            self._loaded = True
            logger.info("ConsistencyEvaluator loaded")
        except Exception as e:
            raise ConsistencyError(
                f"Could not load the consistency evaluation model. "
                f"Check your internet connection. Details: {e}"
            )

    def extract_embedding(self, image: Image.Image) -> np.ndarray:
        """
        Extract a normalised CLIP embedding from an image.

        Args:
            image: PIL Image (panel or character reference).

        Returns:
            Numpy array with shape (embedding_dim,).
        """
        self._ensure_loaded()
        torch = _require_torch()
        try:
            img_tensor = self._preprocess(image).unsqueeze(0).to(self._device)
            with torch.no_grad():
                embedding = self._model.encode_image(img_tensor)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)
            return embedding.cpu().numpy().flatten()
        except Exception as e:
            raise ConsistencyError(f"Embedding extraction failed: {e}")

    def compute_similarity(
        self,
        embedding_a: np.ndarray,
        embedding_b: np.ndarray,
    ) -> float:
        """
        Compute cosine similarity between two normalised embeddings.

        Returns:
            Similarity score in [0, 1].
        """
        similarity = float(np.dot(embedding_a, embedding_b))
        return max(0.0, min(1.0, similarity))

    def evaluate_character_consistency(
        self,
        character_name: str,
        reference_embedding: np.ndarray,
        panel_images: List[Image.Image],
    ) -> Dict[str, Any]:
        """
        Evaluate how consistently a character appears across multiple panels.

        Args:
            character_name:      Name of the character being evaluated.
            reference_embedding: CLIP embedding of the character reference.
            panel_images:        List of PIL Images (panels featuring this character).

        Returns:
            Dict with ``character``, ``average_score``, ``min_score``,
            ``max_score``, and ``panel_scores``.
        """
        if not panel_images:
            return {
                "character": character_name,
                "average_score": 0.0,
                "min_score": 0.0,
                "max_score": 0.0,
                "panel_scores": [],
            }

        logger.info(
            "Evaluating consistency for '%s' across %d panel(s)",
            character_name, len(panel_images),
        )
        try:
            panel_embeddings = [self.extract_embedding(img) for img in panel_images]
            scores = [
                self.compute_similarity(reference_embedding, emb)
                for emb in panel_embeddings
            ]
            result = {
                "character": character_name,
                "average_score": float(np.mean(scores)),
                "min_score": float(np.min(scores)),
                "max_score": float(np.max(scores)),
                "panel_scores": scores,
            }
            logger.info(
                "Consistency '%s': avg=%.3f min=%.3f max=%.3f",
                character_name,
                result["average_score"],
                result["min_score"],
                result["max_score"],
            )
            return result
        except Exception as e:
            raise ConsistencyError(
                f"Failed to evaluate consistency for '{character_name}': {e}"
            )


class ConsistencyService:
    """High-level consistency evaluation service."""

    def __init__(self):
        """Initialise with a lazy evaluator (never raises at import time)."""
        self.evaluator = ConsistencyEvaluator()

    def evaluate_storyboard(
        self,
        characters: Dict[str, Dict[str, Any]],
        shots: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Evaluate consistency for all characters across the entire storyboard.

        Args:
            characters: Dict[name -> {embedding, …}].
            shots:      List of shot dicts with ``image_path`` and ``characters``.

        Returns:
            Dict[name -> consistency_result].
        """
        results = {}

        for char_name, char_data in characters.items():
            panel_images = []
            for shot in shots:
                if char_name in shot.get("characters", []) and shot.get("image_path"):
                    try:
                        panel_images.append(
                            Image.open(shot["image_path"]).convert("RGB")
                        )
                    except Exception as e:
                        logger.warning("Could not load panel %s: %s", shot["image_path"], e)

            if not panel_images:
                logger.info("No panels for '%s'; skipping", char_name)
                continue

            ref_embedding = char_data.get("embedding")
            if ref_embedding is None:
                logger.warning("No reference embedding for '%s'; skipping", char_name)
                continue

            try:
                results[char_name] = self.evaluator.evaluate_character_consistency(
                    char_name, ref_embedding, panel_images
                )
            except ConsistencyError as e:
                logger.error("Consistency check failed for '%s': %s", char_name, e)
                results[char_name] = {"character": char_name, "error": str(e)}

        return results


def get_consistency_service() -> ConsistencyService:
    """Return a configured ConsistencyService instance."""
    return ConsistencyService()
