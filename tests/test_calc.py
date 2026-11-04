"""Hesaplama motoru testleri."""

import pytest

from app.core import calc
from app.core import factors as F


def test_dogalgaz_zinciri():
    """58.400 m3 dogal gaz -> ~123,8 tCO2 (proje metnindeki ornek)."""
    r = calc.hesapla("dogalgaz", 58_400)
    assert r.scope == 1
    assert r.energy_gj == pytest.approx(2207.52, rel=1e-4)
    assert r.co2_kg / 1000 == pytest.approx(123.84, rel=1e-3)
    # CH4 ve N2O eklenince toplam biraz artar ama %1'den az
    assert r.co2e_ton == pytest.approx(123.96, rel=1e-3)
    assert "56.1" in r.formula
    assert len(r.steps) == 7


def test_elektrik_yogunluk():
    r = calc.hesapla("elektrik_tr", 1_000_000)
    assert r.scope == 2
    assert r.co2e_kg == pytest.approx(442_000.0)
    assert r.energy_gj is None


def test_birim_uyusmazligi_hata_verir():
    with pytest.raises(ValueError):
        calc.hesapla("dogalgaz", 100, birim="kg")


def test_negatif_miktar_reddedilir():
    with pytest.raises(ValueError):
        calc.hesapla("dogalgaz", -5)


def test_bilinmeyen_faktor():
    with pytest.raises(KeyError):
        calc.hesapla("yok_boyle_bir_sey", 10)


def test_kapsam_toplami():
    s = [calc.hesapla("dogalgaz", 10_000),
         calc.hesapla("elektrik_tr", 10_000),
         calc.hesapla("hurda_celik", 10)]
    t = calc.kapsam_toplami(s)
    assert t["scope1"] > 0 and t["scope2"] > 0 and t["scope3"] > 0
    assert t["toplam"] == pytest.approx(
        t["scope1"] + t["scope2"] + t["scope3"], rel=1e-6)


def test_urun_birimine_dagitim():
    assert calc.urun_birimine_dagit(1447.0, 1000.0) == pytest.approx(1.447)
    with pytest.raises(ValueError):
        calc.urun_birimine_dagit(10.0, 0)


@pytest.mark.parametrize("yil,beklenen", [(2026, 0.10), (2027, 0.20),
                                          (2028, 0.30), (2031, 0.30)])
def test_cbam_marji(yil, beklenen):
    assert calc.cbam_marj(yil) == beklenen


def test_kacinilan_maliyet_proje_ornegi():
    """1.054 tCO2e, 2027 (%20), 75 EUR -> 15.810 EUR."""
    s = calc.kacinilan_maliyet(1054.0, 2027, 75.0)
    assert s["kacinilan_eur"] == pytest.approx(15_810.0)


def test_tum_faktorlerin_kaynagi_var():
    for f in F.all_factors():
        assert f["source"], f"{f['key']} kaynaksiz"
        assert f["tier"] in ("ipcc", "ulusal", "varsayim")
        assert f["scope"] in (1, 2, 3)


def test_faktor_metinden_bulunur():
    assert F.find_factor_key("Doğal gaz tüketimi 100 m3") == "dogalgaz"
    assert F.find_factor_key("Aktif enerji tüketimi 500 kWh") == "elektrik_tr"
    assert F.find_factor_key("Hiçbir şey") is None
