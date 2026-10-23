"""
Script parsing module using a local Ollama LLM (qwen2.5:7b by default).
Converts screenplay text into structured shot lists with camera angles and mood.

Ollama is called via its OpenAI-compatible /v1/chat/completions endpoint.
JSON is extracted from the response with a fallback regex so the module works
even if the model wraps its output in markdown fences.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

import requests

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
# Screenplay template (documented for users)
# ─────────────────────────────────────────────────────────────────────────────

SCREENPLAY_TEMPLATE = """
SCREENPLAY STRUCTURED TEMPLATE FORMAT:

Each scene should follow this format:

SCENE: [Scene number and location]
DESCRIPTION: [Brief scene description]

SHOT: [Shot number]
TYPE: [wide/medium/close-up/extreme-close-up/over-the-shoulder/point-of-view]
ANGLE: [eye-level/high-angle/low-angle/bird's-eye/worm's-eye/dutch-angle]
CHAR: [Character names, comma-separated]
ACTION: [What happens in this shot]
MOOD: [happy/sad/tense/dramatic/peaceful/action/romantic/mysterious]

Example:
SCENE: 1 - INT. COFFEE SHOP - DAY
DESCRIPTION: Two friends meet after years apart.

SHOT: 1
TYPE: wide
ANGLE: eye-level
CHAR: MAYA, RAHUL
ACTION: Maya enters the coffee shop and spots Rahul sitting at a corner table.
MOOD: peaceful

SHOT: 2
TYPE: close-up
ANGLE: eye-level
CHAR: MAYA
ACTION: Maya's face lights up with recognition and joy.
MOOD: happy
"""


class ParserError(Exception):
    """Custom exception for parsing errors."""
    pass


# ───────────────────────────
# Low-level Ollama client
# ───────────────────────────

class OllamaClient:
    """
    Thin wrapper around Ollama's OpenAI-compatible chat endpoint.
    Uses /v1/chat/completions so switching to any OpenAI-compatible backend
    later is trivial (just change the base URL).
    """

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.chat_url = f"{self.base_url}/v1/chat/completions"

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: int = 180,
    ) -> str:
        """
        Send a chat request to Ollama and return the assistant message text.

        Args:
            messages:    List of {role, content} dicts.
            temperature: Sampling temperature.
            max_tokens:  Maximum tokens in the completion.
            timeout:     HTTP timeout in seconds (local models can be slow).

        Returns:
            Raw text of the assistant reply.

        Raises:
            ParserError: On network errors, non-200 responses, or empty replies.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        try:
            resp = requests.post(self.chat_url, json=payload, timeout=timeout)
        except requests.exceptions.ConnectionError:
            raise ParserError(
                f"Could not connect to Ollama at {self.base_url}. "
                "Make sure Ollama is running (`ollama serve`) and the model "
                f"'{self.model}' is pulled (`ollama pull {self.model}`)."
            )
        except requests.exceptions.Timeout:
            raise ParserError(
                "Ollama request timed out. The model may be loading for the first "
                "time — wait a moment then try again."
            )

        if resp.status_code != 200:
            raise ParserError(
                f"Ollama returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        if not content:
            raise ParserError("Ollama returned an empty response.")

        return content


# ─────────────────────────────────────────────────────────────────────────────
# JSON extraction helper
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> Dict[str, Any]:
    """
    Extract a JSON object from a model response.

    Handles three common formats:
      - Pure JSON
      - JSON wrapped in ```json ... ``` fences
      - JSON embedded somewhere inside prose text

    Args:
        text: Raw LLM response text.

    Returns:
        Parsed dict.

    Raises:
        ParserError: If no valid JSON object can be found.
    """
    # 1. Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Find the outermost { ... } block
    start = text.find("{")
    if start != -1:
        # Walk from the end to find matching closing brace
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    raise ParserError(
        "The model response did not contain valid JSON. "
        "Please try again — the model may have generated extra prose around the JSON."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main parser class
# ─────────────────────────────────────────────────────────────────────────────

class OllamaScriptParser:
    """
    Screenplay parser backed by a local Ollama model (default: qwen2.5:7b).
    """

    def __init__(self):
        """Initialise the parser and verify Ollama is reachable."""
        self.client = OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens

        # Quick reachability check
        try:
            r = requests.get(
                f"{settings.ollama_base_url}/api/tags", timeout=5
            )
            available = [m["name"] for m in r.json().get("models", [])]
            if settings.ollama_model not in available:
                logger.warning(
                    f"Model '{settings.ollama_model}' not found in Ollama. "
                    f"Available: {available}. Pull it with: "
                    f"ollama pull {settings.ollama_model}"
                )
            else:
                logger.info(
                    f"OllamaScriptParser ready — model: {settings.ollama_model}"
                )
        except requests.exceptions.ConnectionError:
            raise ParserError(
                f"Cannot reach Ollama at {settings.ollama_base_url}. "
                "Start it with `ollama serve`."
            )

    # ─────────────────────── public methods ──────────────────────────────────

    def parse_screenplay(self, screenplay_text: str) -> Dict[str, Any]:
        """
        Parse screenplay text into a structured shot list.

        Args:
            screenplay_text: Raw or template-formatted screenplay text.

        Returns:
            Dict with ``title`` and ``scenes`` (each containing ``shots``).

        Raises:
            ParserError: On LLM or JSON errors.
        """
        logger.info("Parsing screenplay with Ollama (%s)", settings.ollama_model)

        system_prompt = (
            "You are an expert screenplay analyst and storyboard artist.\n"
            "Convert the screenplay into a structured JSON shot list.\n\n"
            + SCREENPLAY_TEMPLATE
            + "\n\nReturn ONLY a valid JSON object — no prose, no markdown fences — "
            "with this exact structure:\n"
            '{\n'
            '  "title": "Scene title",\n'
            '  "scenes": [\n'
            '    {\n'
            '      "scene_number": 1,\n'
            '      "location": "INT. COFFEE SHOP - DAY",\n'
            '      "description": "Brief description",\n'
            '      "shots": [\n'
            '        {\n'
            '          "shot_number": 1,\n'
            '          "shot_type": "wide",\n'
            '          "camera_angle": "eye-level",\n'
            '          "characters": ["MAYA", "RAHUL"],\n'
            '          "action": "What happens",\n'
            '          "mood": "peaceful"\n'
            '        }\n'
            '      ]\n'
            '    }\n'
            '  ]\n'
            '}\n\n'
            "Shot types: wide, medium, close-up, extreme-close-up, "
            "over-the-shoulder, point-of-view\n"
            "Camera angles: eye-level, high-angle, low-angle, bird's-eye, "
            "worm's-eye, dutch-angle\n"
            "Moods: happy, sad, tense, dramatic, peaceful, action, romantic, mysterious"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Convert this screenplay into the structured JSON storyboard "
                    f"format:\n\n{screenplay_text}"
                ),
            },
        ]

        raw = self.client.chat(
            messages, temperature=self.temperature, max_tokens=self.max_tokens
        )

        result = _extract_json(raw)

        if "scenes" not in result:
            raise ParserError(
                "LLM response is missing the 'scenes' field. "
                "Try again — the model may have produced an unexpected structure."
            )

        scene_count = len(result["scenes"])
        shot_count = sum(len(s.get("shots", [])) for s in result["scenes"])
        logger.info("Parsed %d scene(s), %d shot(s)", scene_count, shot_count)
        return result

    def suggest_alternative_angles(
        self, shot: Dict[str, Any], scene_context: str
    ) -> List[Dict[str, str]]:
        """
        Generate 1-2 alternative camera angle/mood suggestions for a shot.

        Args:
            shot:          Shot dict with current configuration.
            scene_context: Title or brief description of the overall scene.

        Returns:
            List of suggestion dicts (may be empty on failure).
        """
        prompt = (
            "Given this storyboard shot, suggest 1-2 alternative camera angles "
            "or moods that could enhance the storytelling.\n\n"
            f"Current shot:\n"
            f"- Type: {shot.get('shot_type')}\n"
            f"- Angle: {shot.get('camera_angle')}\n"
            f"- Mood: {shot.get('mood')}\n"
            f"- Action: {shot.get('action')}\n"
            f"Scene context: {scene_context}\n\n"
            "Return ONLY valid JSON (no markdown, no prose):\n"
            '{"suggestions": [{"shot_type": "...", "camera_angle": "...", '
            '"mood": "...", "reason": "..."}]}\n'
            "Limit to 1-2 suggestions."
        )

        try:
            raw = self.client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=512,
            )
            result = _extract_json(raw)
            suggestions = result.get("suggestions", [])[:2]
            logger.info("Generated %d alternative suggestion(s)", len(suggestions))
            return suggestions
        except Exception as exc:
            logger.warning("Alternative angles failed: %s", exc)
            return []

    def validate_and_fix_structure(self, text: str) -> str:
        """
        Return the text unchanged if it already looks structured;
        otherwise ask the LLM to reformat it.

        Args:
            text: Raw screenplay text.

        Returns:
            Template-formatted text (or the original on LLM failure).
        """
        has_structure = any(
            kw in text.upper()
            for kw in ("SCENE:", "SHOT:", "ACTION:", "TYPE:", "ANGLE:")
        )

        if has_structure:
            logger.info("Screenplay already follows template structure — skipping reformat")
            return text

        logger.info("Screenplay is unstructured — asking model to reformat it")
        prompt = (
            f"Convert this screenplay text into the structured template below.\n\n"
            f"{SCREENPLAY_TEMPLATE}\n\n"
            f"Screenplay:\n{text}\n\n"
            "Return only the reformatted screenplay text in template format."
        )

        try:
            return self.client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            logger.warning("Structure fix failed (%s) — using original text", exc)
            return text


# ─────────────────────────────────────────────────────────────────────────────
# Service wrapper
# ─────────────────────────────────────────────────────────────────────────────

class ScriptParsingService:
    """High-level service used by the API layer."""

    def __init__(self):
        """Initialise; degrades gracefully if Ollama is unreachable."""
        try:
            self.parser: Optional[OllamaScriptParser] = OllamaScriptParser()
        except ParserError as exc:
            logger.warning("ScriptParsingService unavailable: %s", exc)
            self.parser = None

    def parse(self, screenplay_text: str, validate: bool = True) -> Dict[str, Any]:
        """
        Parse screenplay into a structured shot list.

        Args:
            screenplay_text: Raw screenplay text.
            validate:        If True, reformat unstructured input first.

        Returns:
            Parsed structure dict.

        Raises:
            ParserError: If the parser is unavailable or parsing fails.
        """
        if not self.parser:
            raise ParserError(
                "Script parser is not available. Make sure Ollama is running "
                f"(`ollama serve`) and the model '{settings.ollama_model}' "
                f"is pulled (`ollama pull {settings.ollama_model}`)."
            )

        if validate:
            screenplay_text = self.parser.validate_and_fix_structure(screenplay_text)

        return self.parser.parse_screenplay(screenplay_text)

    def get_alternative_angles(
        self, shot: Dict[str, Any], scene_context: str = ""
    ) -> List[Dict[str, str]]:
        """Get 1-2 alternative angle/mood suggestions for a shot."""
        if not self.parser:
            return []
        return self.parser.suggest_alternative_angles(shot, scene_context)


def get_parser_service() -> ScriptParsingService:
    """Return a configured ScriptParsingService instance."""
    return ScriptParsingService()


def get_template_documentation() -> str:
    """Return the screenplay template format documentation string."""
    return SCREENPLAY_TEMPLATE
