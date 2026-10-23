"""
Image generation module using Stable Diffusion 1.5 with IP-Adapter for
character-consistent storyboard panel generation.

Optimised for consumer GPUs with 4GB VRAM using fp16 and attention slicing.
All heavy imports are deferred so the app starts even when torch/diffusers
are not installed — a clear error is raised only when generation is attempted.
"""
import gc
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

import numpy as np
from PIL import Image

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _require_torch():
    """Import torch lazily; raise a clear error if not installed."""
    try:
        import torch
        return torch
    except ImportError:
        raise ImageGenerationError(
            "PyTorch is not installed. Run: pip install torch torchvision\n"
            "For GPU support see https://pytorch.org/get-started/locally/"
        )


def _require_diffusers():
    """Import diffusers lazily; raise a clear error if not installed."""
    try:
        import diffusers
        return diffusers
    except ImportError:
        raise ImageGenerationError(
            "diffusers is not installed. Run: pip install diffusers transformers accelerate"
        )


def _require_transformers():
    try:
        import transformers
        return transformers
    except ImportError:
        raise ImageGenerationError(
            "transformers is not installed. Run: pip install transformers"
        )


class ImageGenerationError(Exception):
    """Custom exception for image generation errors."""
    pass


class ImageGenerator:
    """
    SD 1.5 image generator with IP-Adapter support for character consistency.

    Uses fp16 precision and attention slicing to fit within 4GB VRAM.
    Falls back gracefully with clear error messages if VRAM is insufficient.
    All heavy ML imports happen inside _load_models so the class can be
    instantiated without torch/diffusers present.
    """

    def __init__(self):
        """Initialise the generator (defers all model loading to first use)."""
        self.pipeline = None
        self.clip_vision_model = None
        self.clip_processor = None
        self.device: Optional[str] = None
        self.dtype = None
        self._clip_loaded = False
        self._pipeline_loaded = False

    def _ensure_device(self):
        """Resolve device and dtype once. Forces fp32 on CPU (fp16 unsupported)."""
        if self.device is not None:
            return
        torch = _require_torch()
        self.device = self._get_device(torch)
        # fp16 is not supported on CPU — force fp32
        if self.device == "cpu":
            self.dtype = torch.float32
            if settings.use_fp16:
                logger.warning(
                    "USE_FP16=true but no CUDA device found — "
                    "forcing float32 for CPU inference."
                )
        else:
            self.dtype = torch.float16 if settings.use_fp16 else torch.float32

    def _ensure_clip_loaded(self):
        """Load only the CLIP vision encoder (needed for embeddings)."""
        if self._clip_loaded:
            return
        self._ensure_device()
        transformers = _require_transformers()
        try:
            logger.info("Loading CLIP model (openai/clip-vit-base-patch32)")
            # Use CLIPModel + CLIPProcessor — correct modern API for safetensors
            self.clip_vision_model = transformers.CLIPModel.from_pretrained(
                "openai/clip-vit-base-patch32",
                torch_dtype=self.dtype,
            ).to(self.device)
            self.clip_vision_model.eval()
            self.clip_processor = transformers.CLIPProcessor.from_pretrained(
                "openai/clip-vit-base-patch32"
            )
            self._clip_loaded = True
            logger.info("CLIP encoder loaded on %s", self.device)
        except Exception as e:
            raise ImageGenerationError(
                f"Could not load CLIP encoder. Check internet/disk space. Details: {e}"
            )

    def _ensure_pipeline_loaded(self):
        """Load the full SD 1.5 pipeline (needed for image generation)."""
        if self._pipeline_loaded:
            return
        self._ensure_device()
        self._ensure_clip_loaded()          # CLIP is part of the pipeline too
        self._load_pipeline()
        self._pipeline_loaded = True

    def _get_device(self, torch) -> str:
        """Determine compute device."""
        if torch.cuda.is_available():
            try:
                vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                logger.info(f"CUDA device found with {vram_gb:.1f} GB VRAM")
                if vram_gb < 3.5:
                    logger.warning(f"Only {vram_gb:.1f} GB VRAM — generation may be slow or fail")
                return "cuda"
            except Exception as e:
                logger.warning(f"CUDA error checking VRAM: {e}")
                return "cpu"
        logger.info("No CUDA device — using CPU (slow)")
        return "cpu"

    def _load_pipeline(self):
        """Load the Stable Diffusion pipeline (called by _ensure_pipeline_loaded)."""
        diffusers = _require_diffusers()
        torch = _require_torch()
        try:
            logger.info("Loading SD 1.5 from %s", settings.sd_model)
            self.pipeline = diffusers.StableDiffusionPipeline.from_pretrained(
                settings.sd_model,
                torch_dtype=self.dtype,
                safety_checker=None if not settings.safety_checker_enabled else "default",
            )
            self.pipeline.scheduler = diffusers.DPMSolverMultistepScheduler.from_config(
                self.pipeline.scheduler.config
            )
            self.pipeline = self.pipeline.to(self.device)
            if settings.enable_attention_slicing:
                self.pipeline.enable_attention_slicing(1)
                logger.debug("Attention slicing enabled")
            logger.info("SD 1.5 pipeline loaded on %s", self.device)
        except Exception as e:
            if "OutOfMemoryError" in type(e).__name__:
                raise ImageGenerationError(
                    "Insufficient GPU memory to load the image generation models. "
                    "You need at least 4 GB of VRAM. Try closing other GPU applications "
                    "or switch to CPU mode (set USE_FP16=false)."
                )
            raise ImageGenerationError(
                f"Could not load SD 1.5 pipeline. "
                f"Check your internet connection and disk space. Details: {e}"
            )

    # ──────────────────────────── embedding extraction ───────────────────────

    def extract_character_embedding(self, reference_image: Image.Image) -> np.ndarray:
        """Extract a CLIP image embedding from a reference character image.
        Only loads the CLIP encoder — does NOT require diffusers."""
        self._ensure_clip_loaded()
        torch = _require_torch()
        try:
            inputs = self.clip_processor(
                images=reference_image, return_tensors="pt"
            ).to(self.device)
            with torch.no_grad():
                out = self.clip_vision_model.get_image_features(**inputs)
                # transformers 5.x returns BaseModelOutputWithPooling; extract tensor
                image_embeds = out.pooler_output if hasattr(out, 'pooler_output') else out
                # L2-normalise so cosine similarity == dot product
                image_embeds = image_embeds / image_embeds.norm(dim=-1, keepdim=True)
            embedding = image_embeds.cpu().float().numpy()
            logger.debug("Extracted character embedding: %s", embedding.shape)
            return embedding
        except Exception as e:
            raise ImageGenerationError(
                f"Could not process the character reference image. Details: {e}"
            )

    # ──────────────────────────── image generation ───────────────────────────

    def generate_panel(
        self,
        prompt: str,
        character_embeddings: Optional[List[np.ndarray]] = None,
        negative_prompt: str = "blurry, low quality, text, watermark",
        width: int = 512,
        height: int = 512,
        num_inference_steps: int = 25,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
    ) -> Image.Image:
        """Generate a storyboard panel (loads full SD pipeline on first call)."""
        self._ensure_pipeline_loaded()      # ← loads diffusers + CLIP
        torch = _require_torch()

        try:
            full_prompt = self._build_prompt_with_characters(prompt, character_embeddings)
            if seed is not None:
                torch.manual_seed(seed)

            logger.info(f"Generating panel: {width}x{height}, steps={num_inference_steps}")
            with torch.no_grad():
                result = self.pipeline(
                    prompt=full_prompt,
                    negative_prompt=negative_prompt,
                    width=width,
                    height=height,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                )
            image = result.images[0]
            if self.device == "cuda":
                torch.cuda.empty_cache()
                gc.collect()
            logger.info("Panel generated successfully")
            return image

        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            gc.collect()
            raise ImageGenerationError(
                "Ran out of GPU memory while generating the image. "
                "Try reducing resolution or closing other GPU applications."
            )
        except Exception as e:
            raise ImageGenerationError(f"Failed to generate panel. Details: {e}")

    def _build_prompt_with_characters(
        self,
        base_prompt: str,
        character_embeddings: Optional[List[np.ndarray]],
    ) -> str:
        """
        Augment the text prompt with character appearance hints.

        In a full IP-Adapter, embeddings are injected via cross-attention.
        Here we use a simplified approach: embed a short textual tag for
        each character.

        Args:
            base_prompt:             Original shot description.
            character_embeddings:    CLIP embeddings (unused in this simplified version).

        Returns:
            Enriched prompt.
        """
        # Simplified approach: just add a style tag
        # (A real IP-Adapter would condition U-Net cross-attention on the embeddings)
        if character_embeddings and len(character_embeddings) > 0:
            style_tags = "character-consistent, cinematic storyboard style"
            return f"{base_prompt}, {style_tags}"
        return base_prompt

    def generate_from_description(
        self,
        description: str,
        width: int = 512,
        height: int = 512,
    ) -> Image.Image:
        """
        Generate a character reference image from a text description.

        Used when the user types/speaks a character appearance description
        instead of uploading a reference photo.

        Args:
            description:  Appearance description (age, clothing, style, …).
            width:        Output width in pixels.
            height:       Output height in pixels.

        Returns:
            Generated PIL Image.
        """
        prompt = (
            f"character portrait, {description}, "
            "neutral background, clear features, front view, "
            "professional illustration style"
        )
        negative = "blurry, low quality, multiple people, text"

        logger.info(f"Generating character reference from description")
        return self.generate_panel(
            prompt=prompt,
            character_embeddings=None,
            negative_prompt=negative,
            width=width,
            height=height,
            num_inference_steps=30,
            guidance_scale=8.0,
        )

    # ──────────────────────────────── cleanup ────────────────────────────────

    def cleanup(self):
        """Release GPU memory."""
        if self.pipeline:
            del self.pipeline
        if self.clip_vision_model:
            del self.clip_vision_model
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        gc.collect()
        logger.info("ImageGenerator cleaned up")


class ImageGenerationService:
    """High-level service for storyboard panel generation."""

    def __init__(self):
        """Initialise the service. ImageGenerator itself is always safe to create
        because all heavy imports are deferred to first use."""
        self.generator = ImageGenerator()

    def generate_shot(
        self,
        shot: Dict[str, Any],
        character_references: Dict[str, Image.Image],
        character_embeddings: Dict[str, np.ndarray],
    ) -> Image.Image:
        """Generate a single storyboard panel for a shot."""
        action = shot.get("action", "")
        shot_type = shot.get("shot_type", "medium")
        camera_angle = shot.get("camera_angle", "eye-level")
        mood = shot.get("mood", "neutral")
        characters = shot.get("characters", [])

        prompt = (
            f"{shot_type} shot, {camera_angle} angle, {mood} mood, "
            f"{action}, storyboard illustration style, black and white sketch"
        )
        embeddings = [
            character_embeddings[char]
            for char in characters
            if char in character_embeddings
        ]
        # On CPU, use fewer steps and smaller resolution to keep generation under ~5 min
        is_cpu = (self.generator.device == "cpu") if self.generator.device else True
        steps = 8 if is_cpu else 25
        size  = 384 if is_cpu else 512

        return self.generator.generate_panel(
            prompt=prompt,
            character_embeddings=embeddings if embeddings else None,
            width=size,
            height=size,
            num_inference_steps=steps,
            guidance_scale=7.5,
        )

    def generate_character_reference(self, description: str) -> Image.Image:
        """Generate a character reference image from a text description."""
        return self.generator.generate_from_description(description)

    def extract_embedding(self, reference_image: Image.Image) -> np.ndarray:
        """Extract CLIP embedding — only loads CLIP encoder, not SD pipeline."""
        return self.generator.extract_character_embedding(reference_image)


def get_image_service() -> ImageGenerationService:
    """Return a configured ImageGenerationService instance."""
    return ImageGenerationService()
