"""Belge çıkarımı ve ajan zinciri testleri."""

import pytest

from app.agents.document_agent import (_aday_satirlar, _miktar_sec, sayiya_cevir,
                                       birim_bul)


@pytest.mark.parametrize("ham,beklenen", [
    ("58 400", 58400.0),
    ("58.400", 58400.0),
    ("1.234,56", 1234.56),
    ("1,234.56", 1234.56),
    ("407 000,00", 407000.0),
    ("12", 12.0),
])
def test_sayiya_cevir(ham, beklenen):
    assert sayiya_cevir(ham) == pytest.approx(beklenen)


def test_birim_sozcuk_icinde_eslesmez():
    # "kalite" icindeki "lt" birim sayilmamali
    assert birim_bul("Urun kalitesi yuksektir") is None
    assert birim_bul("Motorin 4 200 lt") == "lt"
    assert birim_bul("Tuketim 58 400 m3") == "m3"
    assert birim_bul("Tasima 136 800 ton-km") == "ton-km"


def test_miktar_tutari_degil_miktari_secer():
    satir = "Doğal gaz tüketimi             118 000        m3     873 200,00"
    miktar, birim, _ = _miktar_sec(satir, 0)
    assert miktar == pytest.approx(118_000.0)
    assert birim == "m3"


def test_miktar_birim_yoksa_anahtardan_sonrakini_alir():
    satir = "Fatura 2027 Doğal gaz tüketimi 92 400 bedel 679 560,00"
    anahtar_sonu = satir.lower().find("doğal gaz") + len("doğal gaz")
    miktar, birim, _ = _miktar_sec(satir, anahtar_sonu)
    assert birim is None
    assert miktar == pytest.approx(92_400.0)


def test_aday_satirlar_fatura():
    metin = (
        "ÖRNEK ELEKTRİK A.Ş.\n"
        "Okuma Dönemi: 01.03.2027 - 28.03.2027\n"
        "Aktif enerji tüketimi          387 000       kWh     909 450,00\n"
        "Dağıtım bedeli                                         9 120,00\n"
    )
    adaylar = _aday_satirlar(metin)
    assert len(adaylar) == 1
    a = adaylar[0]
    assert a["factor_key"] == "elektrik_tr"
    assert a["value"] == pytest.approx(387_000.0)
    assert a["unit"] == "kWh"
    assert a["period"] == "2027-03"
    assert a["confidence"] >= 0.85


def test_birim_uyusmazligi_guveni_dusurur():
    metin = "Doğal gaz tüketimi   55 000   kg   407 000,00\n"
    a = _aday_satirlar(metin)[0]
    assert a["factor_key"] == "dogalgaz"
    assert a["value"] == pytest.approx(55_000.0)
    assert a["read_unit"] == "kg"
    assert a["confidence"] < 0.90      # onay kuyruğuna düşmeli
