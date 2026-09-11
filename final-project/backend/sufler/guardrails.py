"""Guardrails: input (prompt-injection) + output (PII-маска). Упрощённо — в проде Pipelines/Onyx (ADR-0007)."""
import re

INJECTION_MARKERS = [
    "ignore previous", "ignore all previous", "disregard the above",
    "забудь инструкции", "игнорируй предыдущие", "system prompt",
]

PII_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email]"),
    (re.compile(r"\b\+?\d[\d\s\-()]{8,}\d\b"), "[телефон]"),
    (re.compile(r"\b\d{2}\s?\d{2}\s?\d{6,7}\b"), "[документ]"),
]


def check_input(text: str) -> str:
    low = text.lower()
    if any(m in low for m in INJECTION_MARKERS):
        raise ValueError("Запрос отклонён: подозрение на prompt-injection.")
    return text


def mask_pii(text: str) -> str:
    for pat, repl in PII_PATTERNS:
        text = pat.sub(repl, text)
    return text
