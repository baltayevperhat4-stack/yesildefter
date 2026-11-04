"""Sade dilde açıklama — dil modelinin sayıya dokunmayan kullanımı.

Modele yalnızca KAYITLI veriler verilir ve yalnızca onları anlatması istenir.
Hesap yapmaz, sayı üretmez. Model yoksa işlev None döner ve arayüz açıklama
düğmesini göstermez.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .. import settings_store as A
from ..models import Activity, Finding
from . import prompts as P
from . import provider as llm


def _acik(db: Session) -> bool:
    return llm.kullanilabilir(db) and A.get_bool("llm_aciklama", db)


def satir_acikla(db: Session, activity_id: int, lang: str = "tr") -> Optional[str]:
    """Bir faaliyet satırının neden onay beklediğini anlatır."""
    if not _acik(db):
        return None
    a = db.get(Activity, activity_id)
    if a is None:
        return None
    esik = A.esik(db)
    e = a.emission
    baglam = "\n".join([
        f"Belge: {a.document.filename if a.document else '-'}",
        f"Belgedeki satır: {a.source_line}",
        f"Tanınan kalem: {a.factor_key}",
        f"Miktar: {a.value} {a.unit}",
        f"Dönem: {a.period or 'belirtilmemiş'}",
        f"Güven skoru: %{a.confidence * 100:.0f} (onay eşiği %{esik * 100:.0f})",
        f"Durum: {a.status}",
        f"Sistem notu: {a.note or 'yok'}",
        (f"Hesaplanan emisyon: {e.co2e_kg / 1000:.3f} tCO2e, Kapsam {e.scope}; "
         f"formül: {e.formula}") if e else "Henüz hesaplanmadı.",
    ])
    return llm.sor(P.ACIKLAMA_SISTEM, P.aciklama_kullanici(baglam, lang),
                   max_tokens=400, db=db)


def bulgu_acikla(db: Session, finding_id: int, lang: str = "tr") -> Optional[str]:
    """Bir denetim bulgusunu işletme sahibinin diliyle anlatır."""
    if not _acik(db):
        return None
    b = db.get(Finding, finding_id)
    if b is None:
        return None
    baglam = "\n".join([
        f"Bulgu türü: {b.code}",
        f"Öncelik: {b.severity}",
        f"Sistemin yazdığı metin: {b.message}",
    ])
    return llm.sor(P.ACIKLAMA_SISTEM, P.aciklama_kullanici(baglam, lang),
                   max_tokens=400, db=db)


def envanter_acikla(db: Session, ozet: dict, lang: str = "tr") -> Optional[str]:
    """Panodaki sayıları tek paragrafta anlatır."""
    if not _acik(db):
        return None
    e = ozet.get("envanter", {})
    satirlar = [
        f"Kapsam 1 (doğrudan yakıt): {e.get('scope1')} tCO2e",
        f"Kapsam 2 (satın alınan enerji): {e.get('scope2')} tCO2e",
        f"Kapsam 3 (değer zinciri): {e.get('scope3')} tCO2e",
        f"Toplam: {e.get('toplam')} tCO2e",
        f"Onay bekleyen satır: {ozet.get('bekleyen')}",
        f"Denetim bulgusu: {ozet.get('bulgu_sayi')}",
    ]
    if ozet.get("gomulu"):
        satirlar.append(
            f"Gömülü karbon: {ozet['gomulu']['toplam']} tCO2e/ton ürün")
    if ozet.get("kacinilan"):
        satirlar.append(
            f"Kaçınılan CBAM maliyeti: "
            f"{ozet['kacinilan']['kacinilan_eur']} EUR/yıl")
    if ozet.get("azaltim_tco2e"):
        satirlar.append(
            f"Azaltım potansiyeli: {ozet['azaltim_tco2e']} tCO2e/yıl "
            f"(envanterin %{ozet.get('azaltim_pay', 0)}'i)")
    return llm.sor(P.ACIKLAMA_SISTEM,
                   P.aciklama_kullanici("\n".join(satirlar), lang),
                   max_tokens=500, db=db)


def tedarikci_eposta_taslagi(db: Session, tesis_adi: str, tedarikci: str,
                             malzeme: str, birim: str = "birim") -> Optional[str]:
    """Tedarikçiye gidecek metnin taslağı. Model yoksa None."""
    if not llm.kullanilabilir(db) or not A.get_bool("llm_eposta_taslagi", db):
        return None
    return llm.sor(P.EPOSTA_SISTEM,
                   P.eposta_kullanici(tesis_adi, tedarikci, malzeme, birim),
                   max_tokens=600, db=db)
