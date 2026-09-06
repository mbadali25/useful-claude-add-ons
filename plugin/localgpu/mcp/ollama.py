"""A small HTTP client for a local Ollama, over the standard library only.

Two calls are used: ``/api/embed`` to turn text into vectors and
``/api/generate`` to ask the chat model something. Both are POSTed with an
explicit ``keep_alive`` because the target machine is a laptop with 8 GB of
VRAM and a display attached: the embed model and the 7B chat model do not fit
at the same time, so each one is told up front how briefly to linger.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Iterable, Sequence

# Long enough for a cold model load off an NVMe, short enough that a wedged
# server is reported rather than waited on.
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_EMBED_TIMEOUT = 120.0
DEFAULT_GENERATE_TIMEOUT = 300.0

# Unload promptly. The bootstrap also sets OLLAMA_MAX_LOADED_MODELS=1; this is
# the client half of the same bargain, not a second opinion about it.
DEFAULT_KEEP_ALIVE = "30s"


class OllamaError(RuntimeError):
    """Base class. Every subclass's message names the command that fixes it."""


class OllamaUnavailable(OllamaError):
    """Nothing is listening, or it hung up mid-request."""


class ModelNotPulled(OllamaError):
    """The server is up but does not have that model on disk."""


class OllamaTimeout(OllamaError):
    """The server accepted the request and did not answer in time."""


def _unavailable(url: str, detail: str) -> OllamaUnavailable:
    return OllamaUnavailable(
        f"Cannot reach Ollama at {url} ({detail}).\n"
        "Start it with:  ollama serve\n"
        "If it runs on another host or port, set ollama_url in .localgpu/config.json."
    )


def _model_missing(model: str) -> ModelNotPulled:
    return ModelNotPulled(
        f"Ollama does not have the model '{model}'.\n"
        f"Pull it with:  ollama pull {model}"
    )


class OllamaClient:
    """Stateless apart from the base URL - safe to build per call."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:11434",
        keep_alive: str = DEFAULT_KEEP_ALIVE,
    ) -> None:
        self.url = url.rstrip("/")
        self.keep_alive = keep_alive

    # -- transport ---------------------------------------------------------

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        timeout: float,
        model: str,
    ) -> dict[str, Any]:
        endpoint = f"{self.url}{path}"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = _read_error(exc)
            if exc.code == 404:
                # Ollama answers 404 both for "no such model" and for "no such
                # route". Only the first names a model in the body.
                if "model" in detail.lower():
                    raise _model_missing(model) from exc
                raise OllamaError(
                    f"Ollama at {self.url} has no {path} endpoint (HTTP 404).\n"
                    "That route needs a current Ollama - upgrade it, then retry."
                ) from exc
            raise OllamaError(
                f"Ollama returned HTTP {exc.code} from {path}: {detail or exc.reason}"
            ) from exc
        except socket.timeout as exc:
            raise OllamaTimeout(
                f"Ollama did not answer {path} within {timeout:g}s using '{model}'.\n"
                "A first load of a large model can be slow; if it repeats, check "
                "ollama ps for a model stuck loading."
            ) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, socket.timeout):
                raise OllamaTimeout(
                    f"Ollama did not answer {path} within {timeout:g}s using '{model}'."
                ) from exc
            raise _unavailable(self.url, str(reason)) from exc
        except (ConnectionError, OSError) as exc:  # pragma: no cover - platform noise
            raise _unavailable(self.url, str(exc)) from exc

    # -- calls -------------------------------------------------------------

    def embed(
        self,
        texts: Sequence[str] | str,
        model: str,
        timeout: float = DEFAULT_EMBED_TIMEOUT,
    ) -> list[list[float]]:
        """Embed one string or a batch, in a single request.

        Returns one vector per input, in the order given.
        """
        inputs = [texts] if isinstance(texts, str) else list(texts)
        if not inputs:
            return []
        data = self._post(
            "/api/embed",
            {"model": model, "input": inputs, "keep_alive": self.keep_alive},
            timeout,
            model,
        )
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(inputs):
            raise OllamaError(
                f"Ollama /api/embed returned {_describe(vectors)} for {len(inputs)} "
                f"input(s) using '{model}'. Is '{model}' an embedding model?"
            )
        return [[float(x) for x in vector] for vector in vectors]

    def generate(
        self,
        prompt: str,
        model: str,
        system: str | None = None,
        options: dict[str, Any] | None = None,
        timeout: float = DEFAULT_GENERATE_TIMEOUT,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
        }
        if system:
            payload["system"] = system
        if options:
            payload["options"] = options
        data = self._post("/api/generate", payload, timeout, model)
        return str(data.get("response", ""))

    def list_models(self, timeout: float = DEFAULT_CONNECT_TIMEOUT) -> list[str]:
        """Model names the server already has. Raises the same errors as the rest."""
        endpoint = f"{self.url}/api/tags"
        try:
            with urllib.request.urlopen(endpoint, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise OllamaError(f"Ollama returned HTTP {exc.code} from /api/tags") from exc
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            raise _unavailable(self.url, str(getattr(exc, "reason", exc))) from exc
        return [str(m.get("name", "")) for m in data.get("models", []) or []]

    def require_models(self, models: Iterable[str]) -> None:
        """Fail early, with the pull command, rather than mid-index."""
        have = set(self.list_models())
        # `ollama pull nomic-embed-text` lands as `nomic-embed-text:latest`.
        bare = {name.split(":", 1)[0] for name in have}
        for model in models:
            if model in have or model in bare:
                continue
            raise _model_missing(model)


def _read_error(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", "replace").strip()
    except Exception:  # pragma: no cover - the body is optional
        return ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:400]
    if isinstance(parsed, dict) and "error" in parsed:
        return str(parsed["error"])[:400]
    return raw[:400]


def _describe(value: Any) -> str:
    if value is None:
        return "no 'embeddings' field"
    if isinstance(value, list):
        return f"{len(value)} embedding(s)"
    return type(value).__name__
