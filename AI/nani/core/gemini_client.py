"""N.A.N.I. Direct Google Gemini Client
Fast, direct REST integration supporting Gemini text generation and multimodal Screen Vision.
"""

import httpx
from typing import Dict, Any, Optional, List
from nani.config import Config

class GeminiDirectClient:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-3.1-flash-lite"):
        self.api_key = api_key or Config.GEMINI_API_KEY
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Generates text from Gemini using direct REST API."""
        if not self.is_configured:
            return "[Gemini Error]: API Key not configured in .env"

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        payload: Dict[str, Any] = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ]
        }
        if system_instruction:
            payload["system_instruction"] = {
                "parts": [{"text": system_instruction}]
            }

        try:
            with httpx.Client(timeout=30.0) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        texts = [p.get("text", "") for p in parts if "text" in p]
                        return "".join(texts).strip()
                    return "[Gemini returned empty response]"
                elif res.status_code == 503:
                    # Fallback to secondary model if primary has demand spike
                    return self._fallback_model_generate(prompt, system_instruction)
                else:
                    return f"[Gemini API Error {res.status_code}]: {res.text}"
        except Exception as e:
            return f"[Gemini Connection Exception]: {str(e)}"

    def _fallback_model_generate(self, prompt: str, system_instruction: Optional[str]) -> str:
        """Tries alternative Gemini model on spike."""
        alt_model = "gemini-3.8-flash" if self.model == "gemini-3.1-flash-lite" else "gemini-3.1-flash-lite"
        url = f"{self.base_url}/models/{alt_model}:generateContent?key={self.api_key}"
        payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        try:
            with httpx.Client(timeout=25.0) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    return "".join([p.get("text", "") for p in parts if "text" in p]).strip()
        except Exception:
            pass
        return "Model temporarily busy. Retrying..."

    def analyze_image_base64(self, b64_image: str, prompt: str = "Analyze this screen image in detail.") -> str:
        """Sends an image (base64 JPEG) to Gemini for multimodal vision analysis."""
        if not self.is_configured:
            return "[Gemini Vision Error]: API Key not configured in .env"

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_image
                            }
                        }
                    ]
                }
            ],
            "system_instruction": {
                "parts": [
                    {
                        "text": "You are N.A.N.I.'s Vision Eyes inspecting your creator's Linux laptop display. Describe open windows, code, compiler errors, active terminal text, and UI elements with technical precision."
                    }
                ]
            }
        }

        try:
            with httpx.Client(timeout=35.0) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        return "".join([p.get("text", "") for p in parts if "text" in p]).strip()
                    return "No visual text returned."
                else:
                    return f"[Gemini Vision API Error {res.status_code}]: {res.text[:200]}"
        except Exception as e:
            return f"[Gemini Vision Exception]: {str(e)}"
