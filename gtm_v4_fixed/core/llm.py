"""Streaming, GPT-5-aware structured-output helper with retries + model fallback."""
import time
from typing import Any, Dict

import httpx

from core.config import client, traceable, FALLBACK_MODEL, LLM_MAX_RETRIES, anthropic_client, ANTHROPIC_MODEL


def _one_call(model, system, user, schema, temperature, reasoning_effort, timeout, tag):
    kwargs: Dict[str, Any] = dict(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        response_format=schema,
    )
    if model.startswith("gpt-5") or model.startswith("o"):
        kwargs["reasoning_effort"] = reasoning_effort
        print(f"        → LLM ({model}){tag} effort={reasoning_effort} streaming …")
    else:
        kwargs["temperature"] = temperature
        print(f"        → LLM ({model}){tag} temp={temperature} streaming …")
    opts = client.with_options(timeout=httpx.Timeout(timeout, connect=10.0))
    with opts.beta.chat.completions.stream(**kwargs) as stream:
        for _ in stream:
            pass
        final = stream.get_final_completion()
    return final.choices[0].message.parsed


@traceable(run_type="llm", name="parse_llm")
def parse_llm(*, model, system, user, schema, temperature=0.1,
              reasoning_effort="low", timeout=120.0, label=""):
    """Call the model for a structured parse. Retries with exponential backoff,
    then automatically fails over to FALLBACK_MODEL before giving up."""
    tag = f" {label}" if label else ""
    models = [model]
    if FALLBACK_MODEL and FALLBACK_MODEL != model:
        models.append(FALLBACK_MODEL)
    retries = max(1, LLM_MAX_RETRIES)
    last_err = None

    for mi, mdl in enumerate(models):
        for attempt in range(1, retries + 1):
            t = time.time()
            try:
                out = _one_call(mdl, system, user, schema, temperature,
                                reasoning_effort, timeout, tag)
                print(f"        ← LLM done{tag} {time.time() - t:.1f}s"
                      + (f" (fallback {mdl})" if mi else ""))
                return out
            except Exception as e:
                last_err = e
                print(f"        \u26a0 LLM error{tag} ({mdl}, attempt {attempt}/{retries}): "
                      f"{str(e)[:90]}")
                if attempt < retries:
                    time.sleep(min(2 ** (attempt - 1), 8))   # exponential backoff
        if mi + 1 < len(models):
            print(f"        \u21aa failing over to {models[mi + 1]}{tag}")

    raise RuntimeError(f"parse_llm failed{tag} after retries + fallback: {last_err}")


@traceable(run_type="llm", name="enhance_with_claude")
def enhance_with_claude(system: str, user: str, max_tokens: int = 1800) -> str:
    """Plain-text enhancement pass using the Anthropic key (no structured schema).
    Used to sharpen wording/SWOT framing/design copy for the PPTX export.
    Returns the original `user` text unchanged if no Anthropic key/client is
    configured, so the export tool degrades gracefully without it."""
    if anthropic_client is None:
        return user
    try:
        msg = anthropic_client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
        text = "\n".join(parts).strip()
        return text or user
    except Exception as e:
        print(f"        \u26a0 Claude enhancement skipped: {str(e)[:90]}")
        return user
