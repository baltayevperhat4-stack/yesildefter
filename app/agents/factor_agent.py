"""Faktör ajanı — faaliyet verisini doğru emisyon faktörüne bağlar ve hesaplar.

İki görevi var:

1. Hesaplama. Onaylı her faaliyet satırını, kaynağı belli bir emisyon
   faktörüyle CO2e'ye çevirir. Tedarikçi gerçek değerini bildirmişse varsayım
   faktörü yerine o değer kullanılır ve kayıt "tedarikci" düzeyiyle saklanır.

2. Süreklilik. Faktör tablosunun sürümü değiştiğinde, eski sürümle
   hesaplanmış kayıtları bulur, yeniden çalıştırır ve farkı raporlar. Karbon
   muhasebesi tek seferlik bir rapor değildir.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import calc
from ..core import factors as F
from ..messages import mesaj
from ..models import Activity, Document, Emission, Supplier
from .base import Agent, AgentResult, iz_birak


def tedarikci_degerleri(db: Session, facility_id: int | None
                        ) -> Dict[str, Tuple[float, str]]:
    """Yanıt vermiş tedarikçilerin bildirdiği faktör değerleri.

    Aynı faktör için birden çok tedarikçi yanıt verdiyse en son yanıt geçerlidir.
    Yalnızca yoğunluk faktörleri değiştirilebilir; yakıtın kalorifik değeri
    tedarikçiye göre değişmez.
    """
    if facility_id is None:
        return {}
    cikti: Dict[str, Tuple[float, str]] = {}
    q = select(Supplier).where(Supplier.facility_id == facility_id,
                               Supplier.status == "yanitladi")
    for t in db.scalars(q):
        if not t.factor_key or t.reported_kgco2e_per_unit is None:
            continue
        if t.factor_key not in F.INTENSITIES:
            continue
        cikti[t.factor_key] = (float(t.reported_kgco2e_per_unit),
                               f"Tedarikçi beyanı — {t.name}")
    return cikti


def _hesapla_ve_yaz(db: Session, a: Activity,
                    override: Dict[str, Tuple[float, str]] | None = None
                    ) -> tuple[bool, str]:
    override = override or {}
    deger, kaynak = override.get(a.factor_key, (None, ""))
    try:
        r = calc.hesapla(a.factor_key, a.value, a.unit,
                         override_kgco2e_per_unit=deger, override_source=kaynak)
    except Exception as exc:
        return False, str(exc)
    e = a.emission
    if e is None:
        e = Emission(activity_id=a.id)
        db.add(e)
    e.scope = r.scope
    e.co2e_kg = r.co2e_kg
    e.energy_gj = r.energy_gj
    e.factor_version = r.factor_version
    e.factor_tier = r.factor_tier
    e.factor_source = r.factor_source
    e.formula = r.formula
    e.steps = r.steps
    a.emission = e
    return True, ""


def _onaysizlari_temizle(db: Session, facility_id: int | None) -> int:
    """Onaylı olmayan satırların eski hesabını siler.

    Reddedilen bir satırın hesabı veri tabanında kalırsa, dışa aktarımlarda
    ve denetimde hayalet kayıt olur.
    """
    q = select(Activity).where(Activity.status != "onayli")
    if facility_id is not None:
        q = q.join(Document).where(Document.facility_id == facility_id)
    silinen = 0
    for a in db.scalars(q):
        if a.emission is not None:
            db.delete(a.emission)
            a.emission = None
            silinen += 1
    return silinen


class FactorAgent(Agent):
    name = "faktor"
    title_tr = "Faktör ajanı"

    def run(self, db: Session, facility_id: int | None = None,
            document_id: int | None = None, **kw) -> AgentResult:
        override = tedarikci_degerleri(db, facility_id)

        q = select(Activity).where(Activity.status == "onayli")
        if document_id is not None:
            q = q.where(Activity.document_id == document_id)
        elif facility_id is not None:
            q = q.join(Document).where(Document.facility_id == facility_id)

        satirlar: List[Activity] = list(db.scalars(q))
        basarili, hatalar = 0, []
        for a in satirlar:
            ok, hata = _hesapla_ve_yaz(db, a, override)
            if ok:
                basarili += 1
            else:
                hatalar.append(f"#{a.id}: {hata}")

        temizlenen = _onaysizlari_temizle(db, facility_id)
        db.flush()
        iz_birak(db, "facility", facility_id, "faktor.hesap",
                 {"hesaplanan": basarili, "hata": len(hatalar),
                  "temizlenen": temizlenen, "tedarikci_faktoru": len(override),
                  "surum": F.FACTOR_SET_VERSION})

        par = {"sayi": basarili, "surum": F.FACTOR_SET_VERSION,
               "tedarikci": len(override)}
        ozet = mesaj("tr", "ajan.faktor.ok", **par)
        if override:
            ozet += mesaj("tr", "ajan.faktor.tedarikci_eki", sayi=len(override))
        return AgentResult(self.name, len(hatalar) == 0, ozet,
                           code="ajan.faktor.ok", params=par,
                           data={"hesaplanan": basarili,
                                 "tedarikci_faktoru": sorted(override),
                                 "surum": F.FACTOR_SET_VERSION},
                           warnings=hatalar[:10])


class FactorRecalcAgent(Agent):
    """Faktör sürümü değiştiğinde etkilenen hesapları yeniden çalıştırır."""

    name = "faktor_yeniden"
    title_tr = "Faktör güncelleme ajanı"

    def run(self, db: Session, facility_id: int | None = None, **kw) -> AgentResult:
        override = tedarikci_degerleri(db, facility_id)

        q = select(Emission).join(Activity).join(Document)
        if facility_id is not None:
            q = q.where(Document.facility_id == facility_id)
        q = q.where(Emission.factor_version != F.FACTOR_SET_VERSION)

        eskiler: List[Emission] = list(db.scalars(q))
        if not eskiler:
            return AgentResult(self.name, True,
                               mesaj("tr", "ajan.faktor_yeniden.guncel"),
                               code="ajan.faktor_yeniden.guncel",
                               data={"yeniden": 0, "fark_tco2e": 0.0,
                                     "surum": F.FACTOR_SET_VERSION})

        fark = 0.0
        for e in eskiler:
            onceki = e.co2e_kg
            ok, _ = _hesapla_ve_yaz(db, e.activity, override)
            if ok:
                fark += (e.co2e_kg - onceki) / 1000.0
        db.flush()
        iz_birak(db, "facility", facility_id, "faktor.yeniden_hesap",
                 {"kayit": len(eskiler), "fark_tco2e": round(fark, 4),
                  "yeni_surum": F.FACTOR_SET_VERSION})
        par = {"sayi": len(eskiler), "fark": f"{fark:+.3f}"}
        return AgentResult(
            self.name, True, mesaj("tr", "ajan.faktor_yeniden.ok", **par),
            code="ajan.faktor_yeniden.ok", params=par,
            data={"yeniden": len(eskiler), "fark_tco2e": round(fark, 4),
                  "surum": F.FACTOR_SET_VERSION},
        )
