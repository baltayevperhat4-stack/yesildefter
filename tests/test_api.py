"""Uçtan uca testler: demo veri, zincir, arayüz ve API.

Not: testler geçici bir veri dizini kullanır; geliştirme veri tabanına
dokunmaz.
"""

import os
import tempfile

import pytest

TMP = tempfile.mkdtemp(prefix="yd_test_")
os.environ["YD_DATA_DIR"] = TMP
os.environ["DATABASE_URL"] = f"sqlite:///{TMP}/test.db"

from fastapi.testclient import TestClient      # noqa: E402

from app.main import app                        # noqa: E402
from app.models import SessionLocal, init_db    # noqa: E402
from app.services import onay_kuyrugu           # noqa: E402
from seed.demo import yukle                     # noqa: E402


@pytest.fixture(scope="module")
def istemci():
    init_db()
    yukle(sifirla=True)
    with TestClient(app) as c:
        yield c


def test_saglik(istemci):
    r = istemci.get("/api/saglik")
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.parametrize("yol", [
    "/", "/belgeler", "/denetim", "/urun", "/azaltim", "/tedarik",
    "/ajanlar", "/faktorler", "/iz",
])
def test_sayfalar_acilir(istemci, yol):
    r = istemci.get(yol)
    assert r.status_code == 200
    assert "YeşilDefter" in r.text


@pytest.mark.parametrize("kod", ["tr", "uz", "ru", "en", "tk"])
def test_dil_degisimi(istemci, kod):
    r = istemci.get(f"/dil/{kod}", follow_redirects=False)
    assert r.status_code == 303
    istemci.cookies.set("yd_lang", kod)
    r2 = istemci.get("/")
    assert r2.status_code == 200


def test_ozet_degerleri_tutarli(istemci):
    o = istemci.get("/api/ozet").json()
    e = o["envanter"]
    assert e["toplam"] == pytest.approx(
        e["scope1"] + e["scope2"] + e["scope3"], rel=1e-6)
    assert e["scope1"] > 0 and e["scope2"] > 0 and e["scope3"] > 0
    assert o["faktor_surumu"]


def test_onay_akisi_envanteri_buyutur(istemci):
    db = SessionLocal()
    try:
        kuyruk = onay_kuyrugu(db, 1)
        assert kuyruk, "demo veride onay bekleyen satır olmalı"
        satir_id = kuyruk[0].id
    finally:
        db.close()

    onceki = istemci.get("/api/ozet").json()["envanter"]["toplam"]
    r = istemci.post(f"/denetim/{satir_id}/onayla", follow_redirects=False)
    assert r.status_code == 303
    sonraki = istemci.get("/api/ozet").json()["envanter"]["toplam"]
    assert sonraki > onceki


def test_cbam_ve_envanter_csv(istemci):
    r = istemci.get("/api/cbam.csv")
    assert r.status_code == 200
    assert "gomulu_toplam" in r.text
    r2 = istemci.get("/api/envanter.csv")
    assert r2.status_code == 200
    assert "Toplam" in r2.text


def test_rapor_dosyalari(istemci):
    x = istemci.get("/api/rapor.xlsx")
    assert x.status_code == 200 and len(x.content) > 5000
    p = istemci.get("/api/rapor.pdf")
    assert p.status_code == 200 and p.content[:4] == b"%PDF"


def test_zincir_tekrar_calistirilabilir(istemci):
    r = istemci.post("/ajanlar/calistir")
    assert r.status_code == 200
    # beş adımın da sonucu sayfada görünmeli
    for ad in ("faktor", "denetim", "uyum", "azaltim", "tedarik"):
        assert ad in r.text


def test_belge_yukleme(istemci):
    icerik = ("ÖRNEK FATURA\nOkuma Dönemi: 01.05.2027 - 28.05.2027\n"
              "Aktif enerji tüketimi   120 000   kWh   280 000,00\n")
    r = istemci.post(
        "/belgeler/yukle",
        files={"dosya": ("test_elektrik.txt", icerik.encode("utf-8"),
                         "text/plain")},
        follow_redirects=True)
    assert r.status_code == 200
    # faktör adı artık arayüz dilinde basılır; miktar ve birim her dilde aynıdır
    assert "kWh" in r.text and "120" in r.text
