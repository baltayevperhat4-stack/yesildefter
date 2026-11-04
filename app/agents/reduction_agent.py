"""Azaltım ajanı — tesisin kendi verisinden önlem üretir.

Her önlem, hangi faaliyet verisinden türetildiğini, kaç tCO2e azalttığını,
yatırımını ve geri ödeme süresini birlikte taşır. Dayanaksız öneri üretmez:
ilgili faaliyet verisi yoksa önlem de yoktur.
"""

from __future__ import annotations

from collections import defaultdict
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..messages import mesaj
from ..models import Activity, Document, Facility, Measure
from .base import Agent, AgentResult, iz_birak

# Model varsayımları — pilot verisiyle değiştirilecektir.
VARSAYIM = {
    "atik_isi_orani": 0.135,       # Kapsam 1 yakıt emisyonunun geri kazanılabilir payı
    "atik_isi_try_per_tco2e": 12_600.0,
    "atik_isi_tasarruf_try_per_tco2e": 6_000.0,
    "ges_ozkullanim": 0.107,       # elektriğin güneşle karşılanabilen payı
    "ges_try_per_tco2e": 17_000.0,
    "ges_tasarruf_try_per_tco2e": 5_900.0,
    "motor_orani": 0.021,          # elektrik emisyonunun verimlilikle azalan payı
    "motor_try_per_tco2e": 5_500.0,
    "motor_tasarruf_try_per_tco2e": 3_900.0,
    "yerel_tedarik_orani": 0.050,  # Kapsam 3 emisyonunun azaltılabilir payı
    "yerel_try_per_tco2e": 2_400.0,
    "yerel_tasarruf_try_per_tco2e": 1_100.0,
}


def _geri_odeme(capex: float, tasarruf: float) -> float:
    if tasarruf <= 0:
        return 0.0
    return round(capex / tasarruf, 2)


class ReductionAgent(Agent):
    name = "azaltim"
    title_tr = "Azaltım ajanı"

    def run(self, db: Session, facility_id: int, **kw) -> AgentResult:
        tesis = db.get(Facility, facility_id)
        if tesis is None:
            return AgentResult(self.name, False, mesaj("tr", "ajan.tesis_yok"),
                               code="ajan.tesis_yok")

        for m in db.scalars(select(Measure).where(Measure.facility_id == facility_id)):
            db.delete(m)
        db.flush()

        satirlar = list(db.scalars(
            select(Activity).join(Document).where(
                Document.facility_id == facility_id,
                Activity.status == "onayli")))

        kapsam_ton = defaultdict(float)
        yakit_ton = 0.0
        elektrik_ton = 0.0
        for a in satirlar:
            if not a.emission:
                continue
            ton = a.emission.co2e_kg / 1000.0
            kapsam_ton[a.emission.scope] += ton
            if a.emission.scope == 1:
                yakit_ton += ton
            if a.factor_key.startswith("elektrik"):
                elektrik_ton += ton

        V = VARSAYIM
        adaylar = []

        if yakit_ton > 0:
            t = yakit_ton * V["atik_isi_orani"]
            capex = t * V["atik_isi_try_per_tco2e"]
            tas = t * V["atik_isi_tasarruf_try_per_tco2e"]
            adaylar.append(("atik_isi", t, capex, tas,
                            {"taban": "taban.kapsam1",
                             "oran": f"{V['atik_isi_orani']:.0%}".rstrip('%')}))

        if elektrik_ton > 0:
            t = elektrik_ton * V["ges_ozkullanim"]
            capex = t * V["ges_try_per_tco2e"]
            tas = t * V["ges_tasarruf_try_per_tco2e"]
            adaylar.append(("ges", t, capex, tas,
                            {"taban": "taban.elektrik",
                             "oran": f"{V['ges_ozkullanim']:.0%}".rstrip('%')}))

            t2 = elektrik_ton * V["motor_orani"]
            capex2 = t2 * V["motor_try_per_tco2e"]
            tas2 = t2 * V["motor_tasarruf_try_per_tco2e"]
            adaylar.append(("motor", t2, capex2, tas2,
                            {"taban": "taban.elektrik",
                             "oran": f"{V['motor_orani']:.1%}".rstrip('%')}))

        if kapsam_ton[3] > 0:
            t = kapsam_ton[3] * V["yerel_tedarik_orani"]
            capex = t * V["yerel_try_per_tco2e"]
            tas = t * V["yerel_tasarruf_try_per_tco2e"]
            adaylar.append(("yerel_tedarik", t, capex, tas,
                            {"taban": "taban.kapsam3",
                             "oran": f"{V['yerel_tedarik_orani']:.0%}".rstrip('%')}))

        if not adaylar:
            return AgentResult(self.name, True,
                               mesaj("tr", "ajan.azaltim.veri_yok"),
                               code="ajan.azaltim.veri_yok",
                               data={"onlem": 0, "toplam_tco2e": 0.0},
                               warnings=[mesaj("tr", "uyari.veri_yukleyin")],
                               warning_codes=["uyari.veri_yukleyin"])

        olusturulan: List[Measure] = []
        for kod, ton, capex, tasarruf, dayanak in adaylar:
            # Türkçe metin dışa aktarım için; ekranda kod+parametre çevrilir.
            tr_dayanak = mesaj("tr", "onlem.dayanak",
                               taban=mesaj("tr", dayanak["taban"]),
                               oran=dayanak["oran"])
            m = Measure(
                facility_id=facility_id, code=kod,
                name=mesaj("tr", f"onlem.{kod}"),
                basis_params=dayanak,
                tco2e_year=round(ton, 2), capex_try=round(capex, 0),
                saving_try_year=round(tasarruf, 0),
                payback_years=_geri_odeme(capex, tasarruf),
                basis=tr_dayanak, selected=1,
            )
            db.add(m)
            olusturulan.append(m)
        db.flush()

        toplam_ton = sum(m.tco2e_year for m in olusturulan)
        toplam_capex = sum(m.capex_try for m in olusturulan)
        toplam_tasarruf = sum(m.saving_try_year for m in olusturulan)
        envanter_ton = sum(kapsam_ton.values())
        pay = (toplam_ton / envanter_ton * 100) if envanter_ton else 0.0

        iz_birak(db, "facility", facility_id, "azaltim.oneri",
                 {"onlem": len(olusturulan), "tco2e": round(toplam_ton, 2)})

        par = {"onlem": len(olusturulan),
               "ton": f"{toplam_ton:,.0f}".replace(",", " "),
               "pay": f"{pay:.0f}"}
        return AgentResult(
            self.name, True, mesaj("tr", "ajan.azaltim.ok", **par),
            code="ajan.azaltim.ok", params=par,
            data={
                "onlem": len(olusturulan),
                "toplam_tco2e": round(toplam_ton, 2),
                "envanter_payi_yuzde": round(pay, 1),
                "toplam_capex_try": round(toplam_capex, 0),
                "toplam_tasarruf_try": round(toplam_tasarruf, 0),
                "agirlikli_geri_odeme_yil": _geri_odeme(toplam_capex, toplam_tasarruf),
            },
        )
