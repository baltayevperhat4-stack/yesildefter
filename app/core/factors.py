"""Emisyon faktörü veri tabanı — sürümlenmiş ve kaynaklı.

Her faktör, kaynağı ve güven düzeyiyle birlikte saklanır. Faktör ajanı bu
tabloyu kullanır; tablo sürümü değiştiğinde etkilenen hesaplar yeniden çalışır.

Güven düzeyleri (tier):
  "ipcc"      — IPCC 2006 varsayılan değeri (uluslararası referans)
  "ulusal"    — ulusal yayımlanmış değer
  "varsayim"  — model varsayımı; pilot verisiyle değiştirilmelidir
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

# Faktör tablosunun sürümü. Değiştiğinde yeniden hesaplama tetiklenir.
FACTOR_SET_VERSION = "2026.10"

# IPCC AR5, 100 yıllık Küresel Isınma Potansiyeli
GWP = {"CO2": 1.0, "CH4": 28.0, "N2O": 265.0}

# Ülkeye göre şebeke elektriği faktörü. Tesisin ülkesi, Kapsam 2'nin hangi
# faktörle hesaplanacağını belirler.
GRID_BY_COUNTRY = {"TR": "elektrik_tr", "UZ": "elektrik_uz"}
DEFAULT_GRID = "elektrik_tr"


def grid_key(ulke: str | None) -> str:
    return GRID_BY_COUNTRY.get((ulke or "").upper(), DEFAULT_GRID)


@dataclass(frozen=True)
class FuelFactor:
    """Yakıt için net kalorifik değer ve emisyon faktörleri."""

    key: str
    name_tr: str
    unit: str              # faaliyet verisinin birimi (m3, lt, kg, ton)
    ncv_mj_per_unit: float  # net kalorifik değer, MJ / birim
    co2_kg_per_gj: float
    ch4_kg_per_tj: float
    n2o_kg_per_tj: float
    scope: int
    tier: str
    source: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IntensityFactor:
    """Doğrudan yoğunluk faktörü (kgCO2e / birim)."""

    key: str
    name_tr: str
    unit: str
    kgco2e_per_unit: float
    scope: int
    tier: str
    source: str

    def as_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------- yakıtlar
FUELS: Dict[str, FuelFactor] = {
    f.key: f
    for f in [
        FuelFactor("dogalgaz", "Doğal gaz", "m3", 37.8, 56.1, 1.0, 0.1, 1,
                   "ipcc", "IPCC 2006, Cilt 2, Tablo 1.4 / 2.2"),
        FuelFactor("motorin", "Motorin (dizel)", "lt", 36.1, 74.1, 3.0, 0.6, 1,
                   "ipcc", "IPCC 2006, Cilt 2, Tablo 1.4 / 3.2.1"),
        FuelFactor("benzin", "Benzin", "lt", 32.2, 69.3, 3.0, 0.6, 1,
                   "ipcc", "IPCC 2006, Cilt 2, Tablo 1.4 / 3.2.1"),
        FuelFactor("lpg", "LPG", "kg", 47.3, 63.1, 1.0, 0.1, 1,
                   "ipcc", "IPCC 2006, Cilt 2, Tablo 1.4 / 2.2"),
        FuelFactor("fuel_oil", "Fuel-oil", "kg", 40.4, 77.4, 3.0, 0.6, 1,
                   "ipcc", "IPCC 2006, Cilt 2, Tablo 1.4 / 2.2"),
        FuelFactor("komur", "Taş kömürü", "kg", 25.8, 94.6, 1.0, 1.5, 1,
                   "ipcc", "IPCC 2006, Cilt 2, Tablo 1.4 / 2.2"),
    ]
}

# ------------------------------------------------- elektrik ve diğerleri
INTENSITIES: Dict[str, IntensityFactor] = {
    f.key: f
    for f in [
        IntensityFactor("elektrik_tr", "Elektrik — Türkiye şebekesi", "kWh",
                        0.442, 2, "varsayim",
                        "Ulusal şebeke emisyon faktörü — model varsayımı; "
                        "resmî güncel değerle değiştirilmelidir"),
        IntensityFactor("elektrik_uz", "Elektrik — Özbekistan şebekesi", "kWh",
                        0.510, 2, "varsayim",
                        "Ulusal şebeke emisyon faktörü — model varsayımı"),
        IntensityFactor("buhar_satin", "Satın alınan buhar", "GJ",
                        66.0, 2, "varsayim",
                        "Satın alınan ısı — model varsayımı"),
        IntensityFactor("hurda_celik", "Hurda çelik (satın alınan)", "ton",
                        430.0, 3, "varsayim",
                        "Öncül malzeme — model varsayımı; tedarikçi verisiyle "
                        "değiştirilmelidir"),
        IntensityFactor("birincil_alum", "Birincil alüminyum", "ton",
                        11500.0, 3, "varsayim",
                        "Öncül malzeme — model varsayımı"),
        IntensityFactor("hurda_alum", "Hurda alüminyum", "ton",
                        600.0, 3, "varsayim",
                        "Öncül malzeme — model varsayımı"),
        IntensityFactor("cimento", "Çimento (satın alınan)", "ton",
                        820.0, 3, "varsayim",
                        "Öncül malzeme — model varsayımı"),
        IntensityFactor("karayolu_tasima", "Karayolu taşıma", "ton-km",
                        0.105, 3, "varsayim",
                        "Yukarı akış taşıma — model varsayımı"),
        IntensityFactor("atik_duzenli", "Düzenli depolama atığı", "ton",
                        480.0, 3, "varsayim",
                        "Atık bertarafı — model varsayımı"),
    ]
}


def get_factor(key: str):
    """Yakıt ya da yoğunluk faktörünü anahtarıyla döndürür."""
    if key in FUELS:
        return FUELS[key]
    if key in INTENSITIES:
        return INTENSITIES[key]
    raise KeyError(f"Bilinmeyen emisyon faktörü: {key}")


def all_factors() -> List[dict]:
    """Tüm faktörleri tek listede, arayüz için."""
    out = []
    for f in FUELS.values():
        d = f.as_dict()
        d["type"] = "fuel"
        out.append(d)
    for f in INTENSITIES.values():
        d = f.as_dict()
        d["type"] = "intensity"
        out.append(d)
    return sorted(out, key=lambda d: (d["scope"], d["key"]))


def factors_for_scope(scope: int) -> List[dict]:
    return [f for f in all_factors() if f["scope"] == scope]


def find_factor_match(text: str, ulke: str | None = None):
    """Serbest metinde faktör anahtarını ve eşleşen kelimenin yerini bulur.

    (anahtar, baslangic, bitis) döndürür; bulunamazsa None. Konum bilgisi,
    miktarın hangi sayı olduğunu seçerken kullanılır.
    """
    t = (text or "").lower()
    eslesme = [
        ("dogalgaz", ["doğal gaz", "dogal gaz", "doğalgaz", "natural gas", "m3 gaz"]),
        ("motorin", ["motorin", "dizel", "diesel", "mazot"]),
        ("benzin", ["benzin", "gasoline", "petrol"]),
        ("lpg", ["lpg", "tüp gaz", "tup gaz", "propan", "bütan"]),
        ("fuel_oil", ["fuel oil", "fuel-oil", "fueloil", "kalorifer yakıtı"]),
        ("komur", ["kömür", "komur", "coal", "linyit"]),
        ("elektrik_tr", ["elektrik", "electricity", "kwh", "enerji tüketim"]),
        ("buhar_satin", ["buhar", "steam"]),
        ("hurda_celik", ["hurda çelik", "hurda celik", "çelik hurda", "scrap steel"]),
        ("birincil_alum", ["birincil alüminyum", "primary aluminium", "külçe alüminyum"]),
        ("hurda_alum", ["hurda alüminyum", "hurda aluminyum", "scrap aluminium"]),
        ("cimento", ["çimento", "cimento", "cement"]),
        ("karayolu_tasima", ["nakliye", "taşıma", "tasima", "freight", "ton-km"]),
        ("atik_duzenli", ["atık", "atik", "waste", "bertaraf"]),
    ]
    sebeke = grid_key(ulke)
    en_iyi = None
    for key, kelimeler in eslesme:
        if key == "elektrik_tr":
            key = sebeke
        for k in kelimeler:
            i = t.find(k)
            if i >= 0 and (en_iyi is None or i < en_iyi[1]):
                en_iyi = (key, i, i + len(k))
    return en_iyi


def find_factor_key(text: str, ulke: str | None = None) -> Optional[str]:
    """Serbest metinden faktör anahtarını tahmin eder (kural tabanlı)."""
    m = find_factor_match(text, ulke)
    return m[0] if m else None
