"""Orkestratör — ajan zincirini yürütür.

Sıra tek yerde tanımlıdır: belge → faktör → denetim → uyum → azaltım → tedarik.
Bir ajan hata verirse zincir durmaz; sonuç listesinde hata olarak taşınır ve
arayüzde görünür. Böylece tek bir bozuk belge tüm envanteri düşürmez.
"""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from .audit_agent import AuditAgent
from .base import AgentResult, iz_birak
from .compliance_agent import ComplianceAgent
from .document_agent import DocumentAgent
from .factor_agent import FactorAgent, FactorRecalcAgent
from .reduction_agent import ReductionAgent
from .supplier_agent import SupplierAgent

AJANLAR = {
    "belge": DocumentAgent(),
    "faktor": FactorAgent(),
    "faktor_yeniden": FactorRecalcAgent(),
    "denetim": AuditAgent(),
    "uyum": ComplianceAgent(),
    "azaltim": ReductionAgent(),
    "tedarik": SupplierAgent(),
}

# Sıra önemlidir: önce hesap, sonra eski sürümlerin yeniden hesabı, sonra
# denetim (hesaplar hazırken), sonra rapor ve öneriler.
ZINCIR = ["faktor", "faktor_yeniden", "denetim", "uyum", "azaltim", "tedarik"]


def ajan_listesi() -> List[dict]:
    return [{"key": k, "title": a.title_tr} for k, a in AJANLAR.items()]


def belge_isle(db: Session, document_id: int) -> AgentResult:
    """Tek belge için belge ajanını çalıştırır."""
    return AJANLAR["belge"](db, document_id=document_id)


def zinciri_calistir(db: Session, facility_id: int,
                     adimlar: List[str] | None = None) -> List[dict]:
    """Tesis için tüm zinciri yürütür ve her adımın sonucunu döndürür."""
    adimlar = adimlar or ZINCIR
    sonuclar: List[dict] = []
    for ad in adimlar:
        ajan = AJANLAR.get(ad)
        if ajan is None:
            sonuclar.append({"agent": ad, "ok": False,
                             "summary": "Bilinmeyen ajan", "data": {},
                             "warnings": [], "duration_ms": 0})
            continue
        res = ajan(db, facility_id=facility_id)
        sonuclar.append(res.as_dict())
    db.commit()
    iz_birak(db, "facility", facility_id, "zincir.calisti",
             {"adim": adimlar, "basarili": sum(1 for s in sonuclar if s["ok"])})
    db.commit()
    return sonuclar
