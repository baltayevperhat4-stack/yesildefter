"""Ajan altyapısı.

Her ajan aynı sözleşmeyi uygular: girdi alır, iş yapar, ne yaptığını denetim
izine yazar ve yapılandırılmış bir sonuç döndürür. Ajanlar birbirini doğrudan
çağırmaz; orkestratör zinciri yürütür. Böylece sıra, tekrar ve hata yönetimi
tek yerde kalır.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..models import AuditEvent


@dataclass
class AgentResult:
    """Ajanın sonucu.

    `summary` Türkçedir ve denetim izine yazılır; arayüz `code` + `params`
    ile aynı cümleyi kullanıcının dilinde kurar. `warning_codes` de aynı
    mantıkla çevrilir."""

    agent: str
    ok: bool
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    duration_ms: int = 0
    code: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    warning_codes: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "agent": self.agent, "ok": self.ok, "summary": self.summary,
            "data": self.data, "warnings": self.warnings,
            "duration_ms": self.duration_ms,
            "code": self.code, "params": self.params,
            "warning_codes": self.warning_codes,
        }


def iz_birak(db: Session, entity: str, entity_id: int | None, action: str,
             detail: dict | None = None, actor: str = "sistem") -> None:
    """Denetim izine tek satır yazar. Hata uygulamayı durdurmaz."""
    try:
        db.add(AuditEvent(entity=entity, entity_id=entity_id, action=action,
                          actor=actor, detail=detail or {}))
        db.flush()
    except Exception:
        db.rollback()


class Agent:
    """Tüm ajanların temel sınıfı."""

    name = "agent"
    title_tr = "Ajan"

    def run(self, db: Session, **kwargs) -> AgentResult:  # pragma: no cover
        raise NotImplementedError

    def __call__(self, db: Session, **kwargs) -> AgentResult:
        t0 = time.perf_counter()
        try:
            res = self.run(db, **kwargs)
        except Exception as exc:
            # Oturum yarım kalmış bir yazma yüzünden bozulmuş olabilir;
            # denetim izini yazabilmek ve zincirin kalanını çalıştırabilmek
            # için önce geri alırız.
            try:
                db.rollback()
            except Exception:
                pass
            res = AgentResult(
                agent=self.name, ok=False,
                summary=f"{self.title_tr} hata verdi: {exc}",
                data={"traceback": traceback.format_exc(limit=3),
                      "hata": str(exc)},
            )
        res.duration_ms = int((time.perf_counter() - t0) * 1000)
        iz_birak(db, "agent", None, f"{self.name}.run",
                 {"ok": res.ok, "summary": res.summary, "ms": res.duration_ms})
        return res
