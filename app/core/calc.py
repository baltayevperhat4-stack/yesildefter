"""GHG hesaplama motoru — GHG Protocol / ISO 14064-1 çerçevesinde.

Her hesap, girdiyi, kullanılan faktörü ve uygulanan formülü birlikte döndürür.
Sonuç tek başına taşınmaz; denetim izi her zaman yanındadır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import factors as F
from .util import sonlu


@dataclass
class CalcResult:
    """Tek bir faaliyet verisinin hesaplanmış emisyonu ve izi."""

    activity_value: float
    activity_unit: str
    factor_key: str
    factor_name: str
    factor_version: str
    factor_tier: str
    factor_source: str
    scope: int
    co2e_kg: float
    co2_kg: float = 0.0
    ch4_co2e_kg: float = 0.0
    n2o_co2e_kg: float = 0.0
    energy_gj: Optional[float] = None
    formula: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def co2e_ton(self) -> float:
        return self.co2e_kg / 1000.0

    def as_dict(self) -> dict:
        d = {
            "activity_value": self.activity_value,
            "activity_unit": self.activity_unit,
            "factor_key": self.factor_key,
            "factor_name": self.factor_name,
            "factor_version": self.factor_version,
            "factor_tier": self.factor_tier,
            "factor_source": self.factor_source,
            "scope": self.scope,
            "co2e_kg": round(self.co2e_kg, 3),
            "co2e_ton": round(self.co2e_ton, 4),
            "co2_kg": round(self.co2_kg, 3),
            "ch4_co2e_kg": round(self.ch4_co2e_kg, 3),
            "n2o_co2e_kg": round(self.n2o_co2e_kg, 3),
            "energy_gj": round(self.energy_gj, 3) if self.energy_gj is not None else None,
            "formula": self.formula,
            "steps": self.steps,
        }
        return d


def hesapla(factor_key: str, miktar: float, birim: Optional[str] = None,
            override_kgco2e_per_unit: Optional[float] = None,
            override_source: str = "") -> CalcResult:
    """Faaliyet verisini CO2e'ye çevirir ve hesap zincirini kaydeder.

    factor_key : emisyon faktörü anahtarı (örn. "dogalgaz")
    miktar     : faaliyet verisi (örn. 58400)
    birim      : verilirse faktörün birimiyle karşılaştırılır
    override_kgco2e_per_unit :
        tedarikçinin bildirdiği gerçek değer. Verilirse varsayım faktörünün
        yerine geçer ve kayıt "tedarikci" düzeyiyle saklanır. Yalnızca
        yoğunluk faktörleri için geçerlidir; yakıtın kalorifik değeri
        tedarikçiye göre değişmez.
    """
    if miktar is None:
        raise ValueError("Faaliyet verisi boş olamaz")
    miktar = sonlu(miktar, "Faaliyet verisi")
    if miktar < 0:
        raise ValueError("Faaliyet verisi negatif olamaz")

    fk = F.get_factor(factor_key)

    if birim and birim.strip().lower() not in (fk.unit.lower(), ""):
        raise ValueError(
            f"Birim uyuşmuyor: belgede '{birim}', faktör '{fk.unit}' bekliyor"
        )

    if isinstance(fk, F.FuelFactor):
        if override_kgco2e_per_unit is not None:
            raise ValueError(
                "Yakıt faktörü tedarikçi değeriyle değiştirilemez; kalorifik "
                "değer ve yanma faktörü tedarikçiye göre değişmez")
        enerji_mj = miktar * fk.ncv_mj_per_unit
        enerji_gj = enerji_mj / 1000.0
        co2 = enerji_gj * fk.co2_kg_per_gj
        ch4 = enerji_gj / 1000.0 * fk.ch4_kg_per_tj * F.GWP["CH4"]
        n2o = enerji_gj / 1000.0 * fk.n2o_kg_per_tj * F.GWP["N2O"]
        toplam = co2 + ch4 + n2o
        adimlar = [
            {"ad": "Faaliyet verisi", "deger": miktar, "birim": fk.unit},
            {"ad": "Net kalorifik değer", "deger": fk.ncv_mj_per_unit,
             "birim": f"MJ/{fk.unit}"},
            {"ad": "Enerji", "deger": round(enerji_gj, 4), "birim": "GJ"},
            {"ad": "CO2 faktörü", "deger": fk.co2_kg_per_gj, "birim": "kgCO2/GJ"},
            {"ad": "CO2", "deger": round(co2, 3), "birim": "kg"},
            {"ad": "CH4 (GWP 28)", "deger": round(ch4, 3), "birim": "kgCO2e"},
            {"ad": "N2O (GWP 265)", "deger": round(n2o, 3), "birim": "kgCO2e"},
        ]
        formul = (
            f"{miktar:,.2f} {fk.unit} × {fk.ncv_mj_per_unit} MJ/{fk.unit} "
            f"÷ 1000 = {enerji_gj:,.3f} GJ; "
            f"× {fk.co2_kg_per_gj} kgCO2/GJ = {co2:,.2f} kgCO2 "
            f"(+CH4 {ch4:,.2f} +N2O {n2o:,.2f} kgCO2e)"
        ).replace(",", " ")
        return CalcResult(
            activity_value=miktar, activity_unit=fk.unit, factor_key=fk.key,
            factor_name=fk.name_tr, factor_version=F.FACTOR_SET_VERSION,
            factor_tier=fk.tier, factor_source=fk.source, scope=fk.scope,
            co2e_kg=toplam, co2_kg=co2, ch4_co2e_kg=ch4, n2o_co2e_kg=n2o,
            energy_gj=enerji_gj, formula=formul, steps=adimlar,
        )

    # yoğunluk faktörü
    yogunluk = fk.kgco2e_per_unit
    duzey, kaynak = fk.tier, fk.source
    if override_kgco2e_per_unit is not None:
        yogunluk = sonlu(override_kgco2e_per_unit, "Tedarikçi değeri")
        if yogunluk < 0:
            raise ValueError("Tedarikçi değeri negatif olamaz")
        duzey = "tedarikci"
        kaynak = override_source or "Tedarikçinin bildirdiği değer"

    toplam = miktar * yogunluk
    adimlar = [
        {"ad": "Faaliyet verisi", "deger": miktar, "birim": fk.unit},
        {"ad": "Yoğunluk faktörü", "deger": yogunluk,
         "birim": f"kgCO2e/{fk.unit}", "duzey": duzey},
        {"ad": "Emisyon", "deger": round(toplam, 3), "birim": "kgCO2e"},
    ]
    formul = (
        f"{miktar:,.2f} {fk.unit} × {yogunluk} kgCO2e/{fk.unit} "
        f"= {toplam:,.2f} kgCO2e"
    ).replace(",", " ")
    return CalcResult(
        activity_value=miktar, activity_unit=fk.unit, factor_key=fk.key,
        factor_name=fk.name_tr, factor_version=F.FACTOR_SET_VERSION,
        factor_tier=duzey, factor_source=kaynak, scope=fk.scope,
        co2e_kg=toplam, co2_kg=toplam, energy_gj=None,
        formula=formul, steps=adimlar,
    )


def kapsam_toplami(sonuclar: List[CalcResult]) -> Dict[str, float]:
    """Kapsam 1/2/3 ve toplam (ton CO2e)."""
    out = {"scope1": 0.0, "scope2": 0.0, "scope3": 0.0}
    for s in sonuclar:
        out[f"scope{s.scope}"] += s.co2e_ton
    out["toplam"] = out["scope1"] + out["scope2"] + out["scope3"]
    return {k: round(v, 4) for k, v in out.items()}


def urun_birimine_dagit(toplam_ton: float, uretim_ton: float) -> float:
    """Gömülü karbon: tCO2e / ton ürün."""
    toplam_ton = sonlu(toplam_ton, "Toplam emisyon")
    uretim_ton = sonlu(uretim_ton, "Üretim miktarı")
    if uretim_ton <= 0:
        raise ValueError("Üretim miktarı sıfırdan büyük olmalıdır")
    return round(toplam_ton / uretim_ton, 6)


def cbam_marj(yil: int) -> float:
    """CBAM'de gerçek veri sunulmadığında uygulanan artış marjı.

    Kaynak: AB CBAM uygulama kuralları — 2026 %10, 2027 %20, 2028+ %30.
    """
    if yil <= 2026:
        return 0.10
    if yil == 2027:
        return 0.20
    return 0.30


def kacinilan_maliyet(gomulu_ton_co2e: float, yil: int,
                      sertifika_eur: float = 75.0) -> dict:
    """Gerçek veri sunarak kaçınılan CBAM ek maliyeti (avro/yıl)."""
    gomulu_ton_co2e = sonlu(gomulu_ton_co2e, "Gömülü karbon")
    sertifika_eur = sonlu(sertifika_eur, "Sertifika fiyatı")
    marj = cbam_marj(yil)
    tutar = gomulu_ton_co2e * marj * sertifika_eur
    return {
        "yil": yil,
        "marj": marj,
        "sertifika_eur": sertifika_eur,
        "gomulu_tco2e": round(gomulu_ton_co2e, 3),
        "kacinilan_eur": round(tutar, 2),
        "formul": (
            f"{gomulu_ton_co2e:,.2f} tCO2e × {marj:.0%} × {sertifika_eur:.0f} €/tCO2e "
            f"= {tutar:,.2f} €"
        ).replace(",", " "),
    }
