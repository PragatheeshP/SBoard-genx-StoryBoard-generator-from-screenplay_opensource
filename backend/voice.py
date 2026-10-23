"""
Voice input module using Sarvam AI for speech-to-text.
Supports Indian languages and code-mixed speech.
"""
import logging
from pathlib import Path
from typing import Union, Optional
import requests

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class VoiceInputError(Exception):
    """Custom exception for voice input errors."""
    pass


class SarvamVoiceService:
    """
    Voice-to-text service using Sarvam AI.
    Supports Indian languages and code-mixed speech.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Sarvam voice service.
        
        Args:
            api_key: Sarvam AI API key. If None, uses value from settings.
        """
        self.api_key = api_key or settings.sarvam_api_key
        self.base_url = "https://api.sarvam.ai/speech-to-text"
        
        if not self.api_key:
            raise VoiceInputError(
                "Sarvam API key not configured. Please set SARVAM_API_KEY "
                "in your environment variables or .env file."
            )
        
        logger.info("Sarvam voice service initialized")
    
    def transcribe(
        self,
        audio_file: Union[str, Path],
        language: str = "hi-IN",
        model: str = "saarika:v1"
    ) -> str:
        """
        Transcribe audio file to text using Sarvam AI.
        
        Args:
            audio_file: Path to audio file (supports wav, mp3, etc.)
            language: Language code (e.g., 'hi-IN', 'ta-IN', 'en-IN')
            model: Sarvam model to use for transcription
            
        Returns:
            Transcribed text
            
        Raises:
            VoiceInputError: If transcription fails
        """
        try:
            audio_path = Path(audio_file)
            if not audio_path.exists():
                raise VoiceInputError(f"Audio file not found: {audio_file}")
            
            logger.info(f"Transcribing audio file: {audio_path.name}")
            
            # Prepare request
            headers = {
                "api-subscription-key": self.api_key
            }
            
            with open(audio_path, 'rb') as f:
                files = {
                    'file': (audio_path.name, f, 'audio/wav')
                }
                data = {
                    'language_code': language,
                    'model': model
                }
                
                # Make API request
                response = requests.post(
                    self.base_url,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=60
                )
            
            # Check response
            if response.status_code == 200:
                result = response.json()
                transcript = result.get('transcript', '')
                
                if not transcript:
                    raise VoiceInputError(
                        "Transcription returned empty text. Please ensure the audio "
                        "contains clear speech and try again."
                    )
                
                logger.info(f"Successfully transcribed {len(transcript)} characters")
                return transcript
            
            elif response.status_code == 401:
                raise VoiceInputError(
                    "Invalid Sarvam API key. Please check your SARVAM_API_KEY "
                    "environment variable."
                )
            
            elif response.status_code == 400:
                error_msg = response.json().get('message', 'Bad request')
                raise VoiceInputError(
                    f"Audio file format not supported or invalid request: {error_msg}"
                )
            
            else:
                raise VoiceInputError(
                    f"Sarvam API request failed with status {response.status_code}: "
                    f"{response.text}"
                )
        
        except VoiceInputError:
            raise
        except requests.exceptions.Timeout:
            logger.error("Sarvam API request timed out")
            raise VoiceInputError(
                "Speech-to-text request timed out. Please try again with a shorter "
                "audio file or check your internet connection."
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during transcription: {e}")
            raise VoiceInputError(
                f"Network error during speech-to-text conversion: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during transcription: {e}")
            raise VoiceInputError(f"Failed to transcribe audio: {str(e)}")


class VoiceInputService:
    """
    High-level voice input service with language detection and preprocessing.
    """
    
    def __init__(self):
        """Initialize voice input service."""
        try:
            self.sarvam = SarvamVoiceService()
        except VoiceInputError as e:
            logger.warning(f"Voice input service initialization warning: {e}")
            self.sarvam = None
    
    def transcribe_screenplay(
        self,
        audio_file: Union[str, Path],
        language: Optional[str] = None
    ) -> str:
        """
        Transcribe screenplay audio to text.
        
        Args:
            audio_file: Path to audio file
            language: Optional language code. If None, defaults to Hindi-English mix
            
        Returns:
            Transcribed screenplay text
            
        Raises:
            VoiceInputError: If service not available or transcription fails
        """
        if not self.sarvam:
            raise VoiceInputError(
                "Voice input service is not available. Please configure your "
                "Sarvam API key to use voice input features."
            )
        
        # Default to Hindi-English for Indian screenplay context
        lang = language or "hi-IN"
        
        try:
            # Transcribe audio
            text = self.sarvam.transcribe(audio_file, language=lang)
            
            # Basic cleanup
            text = text.strip()
            
            # Add newlines for better readability (simple heuristic)
            # This helps the parser identify scene breaks
            text = text.replace(". ", ".\n")
            
            return text
            
        except Exception as e:
            logger.error(f"Screenplay transcription failed: {e}")
            raise


def get_voice_service() -> VoiceInputService:
    """
    Get configured voice input service instance.
    
    Returns:
        Configured VoiceInputService instance
    """
    return VoiceInputService()
