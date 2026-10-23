"""
OCR module with support for Tesseract and PaddleOCR.
Provides a common interface for text extraction from images.
"""
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union
from PIL import Image
import numpy as np

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class OCRBackend(ABC):
    """Abstract base class for OCR backends."""
    
    @abstractmethod
    def extract_text(self, image: Union[str, Path, Image.Image]) -> str:
        """
        Extract text from an image.
        
        Args:
            image: Path to image file or PIL Image object
            
        Returns:
            Extracted text as string
            
        Raises:
            OCRError: If text extraction fails
        """
        pass


class OCRError(Exception):
    """Custom exception for OCR-related errors."""
    pass


class TesseractOCR(OCRBackend):
    """Tesseract OCR backend with Tamil and English language support."""
    
    def __init__(self, languages: str = "tam+eng"):
        """
        Initialize Tesseract OCR.
        
        Args:
            languages: Tesseract language codes (e.g., 'tam+eng' for Tamil and English)
        """
        self.languages = languages
        try:
            import pytesseract
            self.pytesseract = pytesseract
            # Test if Tesseract is installed
            self.pytesseract.get_tesseract_version()
            logger.info(f"Tesseract initialized with languages: {languages}")
        except Exception as e:
            raise OCRError(
                f"Failed to initialize Tesseract. Please ensure Tesseract is installed "
                f"with the required language packs ({languages}). Error: {str(e)}"
            )
    
    def extract_text(self, image: Union[str, Path, Image.Image]) -> str:
        """
        Extract text using Tesseract OCR.
        
        Args:
            image: Path to image file or PIL Image object
            
        Returns:
            Extracted text
        """
        try:
            # Load image if path provided
            if isinstance(image, (str, Path)):
                img = Image.open(image)
            else:
                img = image
            
            # Extract text
            text = self.pytesseract.image_to_string(
                img,
                lang=self.languages,
                config='--psm 6'  # Assume uniform block of text
            )
            
            # Clean up extracted text
            text = text.strip()
            
            if not text:
                logger.warning("Tesseract extracted empty text from image")
                raise OCRError(
                    "No text could be extracted from the image. Please ensure the image "
                    "contains readable text and is of sufficient quality."
                )
            
            logger.info(f"Tesseract extracted {len(text)} characters")
            return text
            
        except OCRError:
            raise
        except Exception as e:
            logger.error(f"Tesseract OCR failed: {str(e)}")
            raise OCRError(f"Failed to extract text with Tesseract: {str(e)}")


class PaddleOCR(OCRBackend):
    """PaddleOCR backend with support for Tamil and English."""
    
    def __init__(self, languages: str = "ta,en"):
        """
        Initialize PaddleOCR.
        
        Args:
            languages: Language codes (e.g., 'ta,en' for Tamil and English)
        """
        self.languages = languages
        try:
            from paddleocr import PaddleOCR as POcr
            
            # Initialize PaddleOCR with specified languages
            lang_list = [lang.strip() for lang in languages.split(',')]
            self.ocr_engines = {}
            
            for lang in lang_list:
                try:
                    self.ocr_engines[lang] = POcr(
                        use_angle_cls=True,
                        lang=lang,
                        use_gpu=False,  # Use CPU for compatibility
                        show_log=False
                    )
                except Exception as e:
                    logger.warning(f"Failed to initialize PaddleOCR for language {lang}: {e}")
            
            if not self.ocr_engines:
                raise OCRError("No PaddleOCR engines could be initialized")
            
            logger.info(f"PaddleOCR initialized with languages: {languages}")
            
        except Exception as e:
            raise OCRError(
                f"Failed to initialize PaddleOCR. Please ensure PaddleOCR and "
                f"PaddlePaddle are installed correctly. Error: {str(e)}"
            )
    
    def extract_text(self, image: Union[str, Path, Image.Image]) -> str:
        """
        Extract text using PaddleOCR.
        
        Args:
            image: Path to image file or PIL Image object
            
        Returns:
            Extracted text
        """
        try:
            # Convert PIL Image to path or numpy array
            if isinstance(image, Image.Image):
                img_array = np.array(image)
            else:
                img_array = str(image)
            
            # Try each language engine
            all_texts = []
            for lang, engine in self.ocr_engines.items():
                try:
                    result = engine.ocr(img_array, cls=True)
                    
                    if result and result[0]:
                        # Extract text from results
                        for line in result[0]:
                            if line and len(line) > 1:
                                text = line[1][0] if isinstance(line[1], tuple) else line[1]
                                all_texts.append(text)
                except Exception as e:
                    logger.warning(f"PaddleOCR extraction failed for {lang}: {e}")
            
            # Combine all extracted text
            text = "\n".join(all_texts).strip()
            
            if not text:
                logger.warning("PaddleOCR extracted empty text from image")
                raise OCRError(
                    "No text could be extracted from the image. Please ensure the image "
                    "contains readable text and is of sufficient quality."
                )
            
            logger.info(f"PaddleOCR extracted {len(text)} characters")
            return text
            
        except OCRError:
            raise
        except Exception as e:
            logger.error(f"PaddleOCR failed: {str(e)}")
            raise OCRError(f"Failed to extract text with PaddleOCR: {str(e)}")


class OCRService:
    """
    OCR service that provides a unified interface for text extraction.
    Supports multiple backends (Tesseract, PaddleOCR) with automatic fallback.
    """
    
    def __init__(self, backend: Optional[str] = None):
        """
        Initialize OCR service with specified backend.
        
        Args:
            backend: OCR backend to use ('tesseract' or 'paddleocr').
                    If None, uses value from settings.
        """
        self.backend_name = backend or settings.ocr_backend
        self.backend: Optional[OCRBackend] = None
        self._initialize_backend()
    
    def _initialize_backend(self):
        """Initialize the OCR backend based on configuration."""
        try:
            if self.backend_name.lower() == "tesseract":
                self.backend = TesseractOCR(languages=settings.tesseract_languages)
            elif self.backend_name.lower() == "paddleocr":
                # Convert tesseract language codes to paddle codes
                paddle_langs = settings.tesseract_languages.replace("tam", "ta").replace("eng", "en")
                self.backend = PaddleOCR(languages=paddle_langs)
            else:
                raise OCRError(
                    f"Unknown OCR backend: {self.backend_name}. "
                    f"Supported backends: tesseract, paddleocr"
                )
            logger.info(f"OCR service initialized with backend: {self.backend_name}")
        except Exception as e:
            logger.error(f"Failed to initialize OCR backend {self.backend_name}: {e}")
            raise
    
    def extract_text(
        self,
        image: Union[str, Path, Image.Image],
        fallback: bool = True
    ) -> str:
        """
        Extract text from an image.
        
        Args:
            image: Path to image file or PIL Image object
            fallback: If True and primary backend fails, try alternative backend
            
        Returns:
            Extracted text
            
        Raises:
            OCRError: If text extraction fails with all attempted backends
        """
        if not self.backend:
            raise OCRError("OCR backend not initialized")
        
        try:
            return self.backend.extract_text(image)
        except OCRError as e:
            if not fallback:
                raise
            
            # Try fallback backend
            logger.warning(f"Primary OCR backend failed, trying fallback: {e}")
            alternative_backend = "paddleocr" if self.backend_name == "tesseract" else "tesseract"
            
            try:
                logger.info(f"Attempting fallback to {alternative_backend}")
                fallback_service = OCRService(backend=alternative_backend)
                return fallback_service.extract_text(image, fallback=False)
            except Exception as fallback_error:
                logger.error(f"Fallback OCR backend also failed: {fallback_error}")
                raise OCRError(
                    f"Text extraction failed with both backends. "
                    f"Primary ({self.backend_name}): {str(e)}. "
                    f"Fallback ({alternative_backend}): {str(fallback_error)}"
                )


def get_ocr_service() -> OCRService:
    """
    Get configured OCR service instance.
    
    Returns:
        Configured OCRService instance
    """
    return OCRService()
