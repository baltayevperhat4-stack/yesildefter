"""Uyum ajanı — CBAM veri seti ve TR ETS raporunu üretir, son tarihleri izler.

Dürüstlük notu: TR ETS pilotu beş sektörde ve 50.000 tCO2e üzerindeki
tesislerde uygulanır. KOBİ genellikle bu kapsama girmez; ajan bunu açıkça
söyler ve yükümlülüğün hangi yoldan geldiğini (tedarikçi / ihracatçı) belirtir.
"""

from __future__ import annotations

import datetime as dt
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings_store as A
from ..core import calc
from ..messages import mesaj
from ..models import Activity, Document, Emission, Facility, Report
from .base import Agent, AgentResult, iz_birak

ETS_ESIK_TCO2E = 50_000.0
ETS_B_ALT, ETS_B_UST = 50_000.0, 500_000.0


def envanter(db: Session, facility_id: int) -> dict:
    """Tesisin kapsam bazında envanterini döndürür."""
    satirlar = list(db.scalars(
        select(Activity).join(Document).where(
            Document.facility_id == facility_id,
            Activity.status == "onayli")))
    kapsam = {1: 0.0, 2: 0.0, 3: 0.0}
    kalem = []
    for a in satirlar:
        if not a.emission:
            continue
        ton = a.emission.co2e_kg / 1000.0
        kapsam[a.emission.scope] += ton
        kalem.append({
            "activity_id": a.id, "factor_key": a.factor_key,
            "period": a.period, "value": a.value, "unit": a.unit,
            "scope": a.emission.scope, "tco2e": round(ton, 4),
            "tier": a.emission.factor_tier,
            "version": a.emission.factor_version,
            "formula": a.emission.formula,
        })
    toplam = sum(kapsam.values())
    return {
        "scope1": round(kapsam[1], 4), "scope2": round(kapsam[2], 4),
        "scope3": round(kapsam[3], 4), "toplam": round(toplam, 4),
        "satir_sayisi": len(kalem), "kalemler": kalem,
    }


def son_tarihler(bugun: dt.date | None = None) -> List[dict]:
    """Yaklaşan uyum son tarihleri (çeyreklik CBAM beyanı örneği)."""
    bugun = bugun or dt.date.today()
    ceyrek_sonlari = [(1, 31), (4, 30), (7, 31), (10, 31)]
    cikti = []
    for ay, gun in ceyrek_sonlari:
        for yil in (bugun.year, bugun.year + 1):
            t = dt.date(yil, ay, gun)
            if t >= bugun:
                cikti.append({
                    "kod": "son_tarih.cbam_ceyrek",
                    "ad": "CBAM çeyreklik beyanı",
                    "tarih": t.isoformat(),
                    "kalan_gun": (t - bugun).days,
                })
                break
    cikti.sort(key=lambda d: d["tarih"])
    return cikti[:3]


class ComplianceAgent(Agent):
    name = "uyum"
    title_tr = "Uyum ajanı"

    def run(self, db: Session, facility_id: int, **kw) -> AgentResult:
        tesis = db.get(Facility, facility_id)
        if tesis is None:
            return AgentResult(self.name, False, mesaj("tr", "ajan.tesis_yok"),
                               code="ajan.tesis_yok")

        env = envanter(db, facility_id)
        uyarilar: List[str] = []

        # --- gömülü karbon (ürün birimine dağıtım)
        gomulu = None
        if tesis.production_ton > 0:
            dogrudan = env["scope1"]
            dolayli = env["scope2"]
            gomulu = {
                "dogrudan_tco2e_ton": calc.urun_birimine_dagit(
                    dogrudan, tesis.production_ton),
                "dolayli_tco2e_ton": calc.urun_birimine_dagit(
                    dolayli, tesis.production_ton),
            }
            gomulu["toplam_tco2e_ton"] = round(
                gomulu["dogrudan_tco2e_ton"] + gomulu["dolayli_tco2e_ton"], 6)
        else:
            uyarilar.append("uyari.uretim_yok")

        # --- CBAM
        cbam = {
            "kapsamda_mi": tesis.export_ton_eu > 0,
            "ab_ihracat_ton": tesis.export_ton_eu,
            "gomulu": gomulu,
        }
        if gomulu and tesis.export_ton_eu > 0:
            gomulu_toplam = gomulu["toplam_tco2e_ton"] * tesis.export_ton_eu
            cbam["ihracatin_gomulu_tco2e"] = round(gomulu_toplam, 3)
            cbam["kacinilan_maliyet"] = calc.kacinilan_maliyet(
                gomulu_toplam, tesis.year, A.cbam_eur(db))
        elif tesis.export_ton_eu <= 0:
            uyarilar.append("uyari.ihracat_yok")

        # --- TR ETS
        toplam = env["toplam"]
        if toplam >= ETS_B_UST:
            kategori, kapsam_ici = "C", True
        elif toplam >= ETS_B_ALT:
            kategori, kapsam_ici = "B", True
        else:
            kategori, kapsam_ici = mesaj("tr", "ets.kategori.kapsam_disi"), False
        ets = {
            "toplam_tco2e": toplam,
            "esik_tco2e": ETS_ESIK_TCO2E,
            "kapsam_ici": kapsam_ici,
            "kategori": kategori,
            # metin değil KOD saklanır; arayüz kullanıcının dilinde kurar
            "aciklama_kodu": ("ets.kapsam_ici" if kapsam_ici
                              else "ets.kapsam_disi"),
            "aciklama": mesaj("tr", "ets.kapsam_ici" if kapsam_ici
                              else "ets.kapsam_disi"),
        }

        rapor = {
            "tesis": {"ad": tesis.name, "ulke": tesis.country,
                      "sektor": tesis.sector, "yil": tesis.year,
                      "uretim_ton": tesis.production_ton,
                      "ab_ihracat_ton": tesis.export_ton_eu},
            "envanter": {k: env[k] for k in
                         ("scope1", "scope2", "scope3", "toplam", "satir_sayisi")},
            "cbam": cbam,
            "ets": ets,
            "son_tarihler": son_tarihler(),
            "uyarilar": uyarilar,
            "cerceve": "GHG Protocol · ISO 14064-1 · IPCC 2006",
            "uretildi": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }

        db.add(Report(facility_id=facility_id, kind="uyum",
                      period=str(tesis.year), payload=rapor))
        db.flush()
        iz_birak(db, "facility", facility_id, "uyum.rapor",
                 {"toplam_tco2e": toplam, "ets_kategori": kategori})

        par = {"toplam": f"{toplam:,.1f}".replace(",", " "),
               "kategori": kategori}
        ozet = mesaj("tr", "ajan.uyum.ok", **par)
        if cbam.get("kacinilan_maliyet"):
            tutar = f"{cbam['kacinilan_maliyet']['kacinilan_eur']:,.0f}".replace(",", " ")
            par["tutar"] = tutar
            ozet += mesaj("tr", "ajan.uyum.kacinilan_eki", tutar=tutar)
        return AgentResult(self.name, True, ozet, code="ajan.uyum.ok",
                           params=par, data=rapor,
                           warnings=[mesaj("tr", u) for u in uyarilar],
                           warning_codes=uyarilar)
