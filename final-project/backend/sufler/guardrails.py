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


class StreamingPiiFilter:
    """Маска ПДн на потоке токенов.

    Маскировать каждый кусок отдельно нельзя: шаблон (почта, телефон) почти
    всегда разрывается границей токена, и наружу уйдут его половинки. Поэтому
    маска применяется к НАКОПЛЕННОМУ тексту целиком, а наружу отдаётся только
    устойчивый префикс — всё, кроме последних `hold` символов.

    Честная граница применимости: шаблон длиннее окна удержания проскочит.
    Окно — 64 символа против самого длинного из текущих шаблонов (~30), запас
    двукратный. Полная маска всё равно накладывается на `flush()`, так что в
    сохранённом ответе ПДн не останется; риск — в уже отданных байтах.
    """

    def __init__(self, hold: int = 64):
        self.hold = hold
        self._acc = ""
        self._sent = 0

    def push(self, delta: str) -> str:
        self._acc += delta
        masked = mask_pii(self._acc)
        stable = max(0, len(masked) - self.hold)
        if stable <= self._sent:
            return ""
        out = masked[self._sent:stable]
        self._sent = stable
        return out

    def flush(self) -> str:
        masked = mask_pii(self._acc)
        out = masked[self._sent:]
        self._sent = len(masked)
        return out

    @property
    def text(self) -> str:
        """Полностью промаскированный ответ — то, что уходит в аудит."""
        return mask_pii(self._acc)

    @property
    def raw(self) -> str:
        """Накопленный текст до маски — чтобы вызывающий видел, сработала ли она."""
        return self._acc
