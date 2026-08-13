"""LLM client — supports Z.ai and OpenAI (via Codex auth)."""

import json
import urllib.request
from pathlib import Path
from typing import Optional

from agents.core.config import ZAI_URL, get_zai_key, get_zai_model

CODEX_AUTH = Path.home() / ".codex" / "auth.json"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _load_codex_token() -> Optional[str]:
    if not CODEX_AUTH.exists():
        return None
    try:
        data = json.loads(CODEX_AUTH.read_text())
        return data.get("tokens", {}).get("access_token")
    except Exception:
        return None


def _detect_provider() -> str:
    if _load_codex_token():
        return "codex"
    if get_zai_key():
        return "zai"
    return "zai"


class LLMClient:
    def __init__(self, api_url: str = None, api_key: str = None, model: str = None, provider: str = None):
        self.provider = provider or _detect_provider()

        if self.provider == "codex":
            self.api_url = api_url or OPENAI_URL
            self.api_key = api_key or _load_codex_token() or ""
            self.model = model or "gpt-4o-mini"
        else:
            self.api_url = api_url or ZAI_URL
            self.api_key = api_key or get_zai_key()
            self.model = model or get_zai_model()

    def _build_body(self, prompt: str, max_tokens: int, temperature: float, json_mode: bool = False) -> dict:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if self.provider == "zai":
            body["thinking"] = {"type": "disabled"}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    async def generate(self, prompt: str, timeout: int = 15, max_tokens: int = 300, temperature: float = 0.9) -> Optional[str]:
        """Generate text. Returns None on failure (never raises, never hangs)."""
        if not self.api_key:
            return None
        try:
            body = self._build_body(prompt, max_tokens, temperature)
            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            )
            resp = urllib.request.urlopen(req, timeout=timeout)
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            return None

    async def generate_json(self, prompt: str, timeout: int = 35, max_tokens: int = 2800, temperature: float = 0.9) -> Optional[dict]:
        """Generate JSON response. Returns None on failure."""
        if not self.api_key:
            return None
        try:
            body = self._build_body(prompt, max_tokens, temperature, json_mode=True)
            req = urllib.request.Request(
                self.api_url,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            )
            resp = urllib.request.urlopen(req, timeout=timeout)
            data = json.loads(resp.read())
            text = (data["choices"][0]["message"]["content"] or "").strip()
            return json.loads(text)
        except Exception:
            return None
