"""Translation backends for the PDF agent.

Supports:
  - mock   : offline demo (no API keys)
  - ollama : local models via Ollama (http://localhost:11434)
  - bedrock: AWS Bedrock (Nova Lite by default)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod


class Translator(ABC):
    name: str

    @abstractmethod
    def translate(self, text: str, target_lang: str) -> str:
        ...


class MockTranslator(Translator):
    """Offline demo backend — prefixes each block so the pipeline is visible."""

    name = "mock"

    def translate(self, text: str, target_lang: str) -> str:
        lang = target_lang.upper()
        return f"[{lang} demo translation]\n{text}"


class OllamaTranslator(Translator):
    """Local models through a running Ollama server."""

    name = "ollama"

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def translate(self, text: str, target_lang: str) -> str:
        prompt = (
            f"Translate the following text to {target_lang}. "
            "Return only the translation, no commentary.\n\n"
            f"{text}"
        )
        payload = json.dumps(
            {"model": self.model, "prompt": prompt, "stream": False}
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Ollama not reachable at {self.base_url}. "
                "Start it with: ollama serve"
            ) from exc
        return body["response"].strip()


class BedrockTranslator(Translator):
    """AWS Bedrock Converse API (Nova Lite by default)."""

    name = "bedrock"

    def __init__(
        self,
        model_id: str = "amazon.nova-lite-v1:0",
        region: str = "us-east-1",
    ):
        self.model_id = model_id
        self.region = region

    def translate(self, text: str, target_lang: str) -> str:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("Install boto3 for Bedrock: pip install boto3") from exc

        client = boto3.client("bedrock-runtime", region_name=self.region)
        prompt = (
            f"Translate the following text to {target_lang}. "
            "Return only the translation, no commentary.\n\n"
            f"{text}"
        )
        try:
            response = client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 4096, "temperature": 0.3},
            )
        except Exception as exc:
            raise RuntimeError(
                f"Bedrock call failed ({self.model_id} in {self.region}). "
                "Check AWS credentials and model access."
            ) from exc
        return response["output"]["message"]["content"][0]["text"].strip()


def get_translator(backend: str, **kwargs) -> Translator:
    if backend == "mock":
        return MockTranslator()
    if backend == "ollama":
        return OllamaTranslator(**kwargs)
    if backend == "bedrock":
        return BedrockTranslator(**kwargs)
    raise ValueError(f"unknown backend {backend!r}; choose mock, ollama, or bedrock")


def auto_backend() -> Translator:
    """Pick the best available backend: bedrock → ollama → mock."""
    try:
        import boto3

        sts = boto3.client("sts")
        sts.get_caller_identity()
        return BedrockTranslator()
    except Exception:
        pass

    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2):
            return OllamaTranslator()
    except Exception:
        pass

    print("Note: using mock translator (no AWS credentials or Ollama found).")
    return MockTranslator()
