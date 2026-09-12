"""Контекст доступа и единая проверка прав (ADR-0016).

Роли берутся из проверенного JWT на границе API и упаковываются в RequestContext
ОДИН раз на запрос. Ниже по стеку контекст только читается: ни агент, ни ретривер
его не конструируют и не меняют. Все проверки прав идут через `allowed()` —
одна функция, одна семантика для векторного и графового путей.
"""
from dataclasses import dataclass, field
from typing import Iterable, Sequence
import uuid

PUBLIC = "all"  # метка общедоступного материала


@dataclass(frozen=True)
class RequestContext:
    """Кто спрашивает. Неизменяем: подмена роли ниже по стеку невозможна."""
    subject: str = "anonymous"
    roles: tuple = (PUBLIC,)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @classmethod
    def of(cls, roles: Iterable[str], subject: str = "anonymous",
           request_id: str = "") -> "RequestContext":
        rr = tuple(r.strip() for r in roles if r and r.strip()) or (PUBLIC,)
        if request_id:
            # Мультиагентный слой (ADR-0015) сужает права для каждого «сотрудника»,
            # но идентификатор запроса обязан остаться общим: иначе шаги одного
            # обращения не сшиваются в аудите и в трейсе.
            return cls(subject=subject, roles=rr, request_id=request_id)
        return cls(subject=subject, roles=rr)


def allowed(acl: Sequence[str], roles: Sequence[str]) -> bool:
    """Deny-by-default: пустой ACL недоступен никому (ADR-0016, инвариант 1)."""
    if not acl:
        return False
    if PUBLIC in acl:
        return True
    return bool(set(acl) & set(roles))
