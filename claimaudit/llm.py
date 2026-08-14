"""
Model access for the demonstrator. Bring your own key.

Anthropic is the default provider. OpenAI and a local Ollama model are kept as
alternatives so the demonstrator can be shown on a laptop with no outbound
network, which matters for a data-residency conversation.

Keys live in Streamlit session state for the life of the browser session. They
are never written to disk, never logged, and never placed in a URL.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any


# --------------------------------------------------------------------------
# Model menu
# --------------------------------------------------------------------------

CORE42 = "Core42 (UAE sovereign)"

PROVIDERS = ["Anthropic", "OpenAI", CORE42, "Ollama (local)"]

ANTHROPIC_MODELS = [
    ("claude-opus-5", "Claude Opus 5 — highest capability, best for clinical judgement"),
    ("claude-sonnet-5", "Claude Sonnet 5 — near-Opus quality, faster and cheaper"),
    ("claude-haiku-4-5", "Claude Haiku 4.5 — fastest; use for a quick walkthrough"),
]

OPENAI_MODELS = [
    ("gpt-4.1", "GPT-4.1"),
    ("gpt-4o", "GPT-4o"),
    ("gpt-4o-mini", "GPT-4o mini — fastest"),
]

# ---------------------------------------------------------------------------
# Core42 — PLACEHOLDER, NOT WIRED UP
#
# Present so the data-residency conversation can be had on the screen rather
# than in the margin. Health claim data is personal data under the UAE PDPL and
# sits inside ADHICS; an insurer that cannot keep inference in-country cannot
# put this platform into production, whatever the audit quality.
#
# Selecting it shows what in-country inference would look like and refuses to
# run. It deliberately does not silently fall back to another provider — a
# sovereignty control that quietly routes offshore is worse than none.
# ---------------------------------------------------------------------------

CORE42_MODELS = [
    ("jais-30b-chat", "JAIS 30B — Arabic-first model, useful for the bilingual "
                      "provider correspondence Squad H produces"),
    ("core42-frontier-hosted", "Frontier model on a Core42 in-country endpoint"),
    ("core42-open-hosted", "Open-weight model on a Core42 in-country endpoint"),
]

CORE42_NOTE = (
    "Illustrative only — no calls are made. This entry marks where in-country "
    "inference would sit: prompts, retrieved policy clauses and generated findings "
    "stay inside UAE jurisdiction, so claim data never crosses a border to be "
    "audited. Wiring it up is an endpoint and credential change, not a redesign — "
    "the agent contract, the retrieval layer and the workbench are provider-agnostic."
)

# Indicative USD per 1M tokens, used only for the run-cost estimate shown in the
# UI. Not a billing source of truth.
PRICING = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
}

REASONING_MODES = {
    "Standard": "The model decides how much to think. Best quality.",
    "Fast": "Thinking off where the model supports it. Quicker and cheaper; "
            "weaker on the clinical-judgement agents.",
}

_THINKING_CAPABLE = ("claude-opus-5", "claude-sonnet-5", "claude-opus-4", "claude-sonnet-4-6")


@dataclass
class LLMConfig:
    provider: str = "Anthropic"
    model: str = "claude-opus-5"
    api_key: str = ""
    base_url: str = "http://localhost:11434"
    reasoning: str = "Standard"
    max_tokens: int = 3000
    timeout_s: int = 180


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    error: str = ""
    model: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


# --------------------------------------------------------------------------
# Client construction
# --------------------------------------------------------------------------


class ProviderError(RuntimeError):
    pass


def build_client(cfg: LLMConfig) -> Any:
    """Create a provider client. Raises ProviderError with a usable message."""
    if cfg.provider == "Anthropic":
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                "The 'anthropic' package is not installed. Run: pip install anthropic"
            ) from exc
        if not cfg.api_key:
            raise ProviderError("Add your Anthropic API key in the sidebar.")
        return anthropic.Anthropic(api_key=cfg.api_key, timeout=cfg.timeout_s, max_retries=2)

    if cfg.provider == "OpenAI":
        try:
            import openai
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                "The 'openai' package is not installed. Run: pip install openai"
            ) from exc
        if not cfg.api_key:
            raise ProviderError("Add your OpenAI API key in the sidebar.")
        return openai.OpenAI(api_key=cfg.api_key, timeout=cfg.timeout_s, max_retries=2)

    if cfg.provider == CORE42:
        raise ProviderError(
            "Core42 is shown as an illustration of in-country inference and is not "
            "connected in this demonstrator. Pick Anthropic, OpenAI or Ollama to run "
            "the fleet — or run the deterministic checks, which need no provider at all."
        )

    if cfg.provider.startswith("Ollama"):
        try:
            import ollama
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                "The 'ollama' package is not installed. Run: pip install ollama"
            ) from exc
        return ollama.Client(host=cfg.base_url, timeout=cfg.timeout_s)

    raise ProviderError(f"Unknown provider: {cfg.provider}")


def check_credentials(cfg: LLMConfig) -> tuple[bool, str]:
    """Cheap round-trip so the user finds out about a bad key before a 280-call run."""
    try:
        client = build_client(cfg)
    except ProviderError as exc:
        return False, str(exc)

    try:
        if cfg.provider == "Anthropic":
            client.messages.create(
                model=cfg.model,
                max_tokens=16,
                messages=[{"role": "user", "content": "Reply with the word OK."}],
            )
        elif cfg.provider == "OpenAI":
            client.chat.completions.create(
                model=cfg.model,
                max_tokens=16,
                messages=[{"role": "user", "content": "Reply with the word OK."}],
            )
        else:
            client.chat(
                model=cfg.model,
                messages=[{"role": "user", "content": "Reply with the word OK."}],
            )
        return True, f"Connected — {cfg.provider} / {cfg.model}."
    except Exception as exc:  # noqa: BLE001 — surface whatever the provider said
        return False, _friendly_error(exc)


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "authentication" in low or "invalid x-api-key" in low or "401" in low:
        return "Authentication failed — check the API key."
    if "not_found" in low or "404" in low:
        return f"Model not found for this key or provider. ({msg[:160]})"
    if "rate" in low and "limit" in low:
        return "Rate limited by the provider. Lower the concurrency and retry."
    if "connection" in low or "refused" in low:
        return f"Could not reach the provider. ({msg[:160]})"
    return msg[:300]


# --------------------------------------------------------------------------
# Single completion
# --------------------------------------------------------------------------


def complete(
    client: Any,
    cfg: LLMConfig,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int | None = None,
) -> LLMResponse:
    """One system+user turn. Returns text; never raises."""
    started = time.perf_counter()
    budget = max_tokens or cfg.max_tokens

    try:
        if cfg.provider == "Anthropic":
            kwargs: dict[str, Any] = {
                "model": cfg.model,
                "max_tokens": budget,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }
            # Thinking is on by default on the current Opus/Sonnet models. "Fast"
            # turns it off where the model supports the switch; on models that do
            # not, we simply send nothing rather than guess.
            if cfg.reasoning == "Fast" and cfg.model.startswith(_THINKING_CAPABLE):
                kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

            resp = client.messages.create(**kwargs)
            text = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            )
            if getattr(resp, "stop_reason", "") == "refusal":
                return LLMResponse(
                    text="",
                    error="The model declined this request (safety refusal).",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    model=cfg.model,
                )
            usage = getattr(resp, "usage", None)
            return LLMResponse(
                text=text,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                latency_ms=int((time.perf_counter() - started) * 1000),
                model=cfg.model,
            )

        if cfg.provider == "OpenAI":
            resp = client.chat.completions.create(
                model=cfg.model,
                max_tokens=budget,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            usage = getattr(resp, "usage", None)
            return LLMResponse(
                text=resp.choices[0].message.content or "",
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                latency_ms=int((time.perf_counter() - started) * 1000),
                model=cfg.model,
            )

        # Ollama
        resp = client.chat(
            model=cfg.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format="json",
            options={"num_predict": budget},
        )
        return LLMResponse(
            text=resp["message"]["content"],
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=cfg.model,
        )

    except Exception as exc:  # noqa: BLE001 — an agent error is a result, not a crash
        return LLMResponse(
            text="",
            error=_friendly_error(exc),
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=cfg.model,
        )


# --------------------------------------------------------------------------
# JSON extraction
# --------------------------------------------------------------------------

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> dict[str, Any] | None:
    """Pull the first well-formed JSON object out of a model response."""
    if not text:
        return None

    candidates: list[str] = []

    fenced = _FENCE.findall(text)
    candidates.extend(f.strip() for f in fenced)
    candidates.append(text.strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Brace-matched scan: tolerant of prose either side of the object.
        start = candidate.find("{")
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(candidate)):
                ch = candidate[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        blob = candidate[start : i + 1]
                        try:
                            parsed = json.loads(blob)
                            if isinstance(parsed, dict):
                                return parsed
                        except json.JSONDecodeError:
                            break
            start = candidate.find("{", start + 1)

    return None


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rate = PRICING.get(model)
    if not rate:
        return 0.0
    return (input_tokens / 1_000_000) * rate[0] + (output_tokens / 1_000_000) * rate[1]
