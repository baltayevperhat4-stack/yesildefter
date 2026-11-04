"""Dayanıklılık ve güvenlik testleri.

Her test, denetimde bulunan gerçek bir kusura karşılık gelir. Amaç, aynı
kusurun sessizce geri gelmesini engellemektir.
"""

import os
import tempfile

import pytest

TMP = tempfile.mkdtemp(prefix="yd_dyn_")
os.environ["YD_DATA_DIR"] = TMP
os.environ["DATABASE_URL"] = f"sqlite:///{TMP}/dyn.db"

from fastapi.testclient import TestClient            # noqa: E402

from app.agents.document_agent import _aday_satirlar, fiyat_satiri_mi  # noqa: E402
from app.core import calc                            # noqa: E402
from app.core import factors as F                    # noqa: E402
from app.core.util import csv_guvenli, sonlu, temiz_metin  # noqa: E402
from app.main import app, guvenli_dosya_adi          # noqa: E402
from app.models import SessionLocal, Supplier, init_db  # noqa: E402
from seed.demo import yukle                          # noqa: E402


@pytest.fixture(scope="module")
def istemci():
    init_db()
    yukle(sifirla=True)
    with TestClient(app) as c:
        yield c


# ----------------------------------------------------------- sayı güvenliği
def test_sonsuz_ve_nan_reddedilir():
    for kotu in (float("inf"), float("-inf"), float("nan")):
        with pytest.raises(ValueError):
            sonlu(kotu)
        with pytest.raises(ValueError):
            calc.hesapla("dogalgaz", kotu)


def test_sonsuz_uretim_kurulumda_reddedilir(istemci):
    # Tesis zaten var; ikinci kurulum yok sayılmalı ve çökmemeli
    r = istemci.post("/kurulum", data={"ad": "X", "uretim": "1e400",
                                       "ihracat": "-5", "yil": "9999"},
                     follow_redirects=False)
    assert r.status_code == 303
    assert istemci.get("/api/ozet").status_code == 200


def test_sifir_uretimde_gomulu_karbon_hata_vermez():
    with pytest.raises(ValueError):
        calc.urun_birimine_dagit(100.0, 0.0)


# ------------------------------------------------------------- metin güvenliği
def test_denetim_karakteri_temizlenir():
    assert "\x00" not in temiz_metin("Hurda \x00\x07 celik")
    assert temiz_metin("abc", 2) == "ab"


def test_csv_formul_enjeksiyonu_engellenir():
    assert csv_guvenli("=CMD()").startswith("'")
    assert csv_guvenli("+1+1").startswith("'")
    assert csv_guvenli("Doğal gaz") == "Doğal gaz"


def test_kontrol_karakterli_belge_raporu_bozmaz(istemci):
    icerik = "Hurda celik alimi 12 \x00\x07 ton\n"
    r = istemci.post("/belgeler/yukle",
                     files={"dosya": ("kirli.txt", icerik.encode("utf-8"),
                                      "text/plain")},
                     follow_redirects=True)
    assert r.status_code == 200
    x = istemci.get("/api/rapor.xlsx")
    assert x.status_code == 200 and len(x.content) > 5000


# -------------------------------------------------------------- dosya adları
@pytest.mark.parametrize("ham", ["..", "/", "", None, "../../etc/passwd",
                                 "a" * 400, "   ", "belge.PDF"])
def test_guvenli_dosya_adi_her_zaman_kullanilabilir(ham):
    ad = guvenli_dosya_adi(ham)
    assert ad and "/" not in ad and ad not in (".", "..")
    assert len(ad) <= 210


def test_bozuk_dosya_adi_cokme_yapmaz(istemci):
    r = istemci.post("/belgeler/yukle",
                     files={"dosya": ("..", b"Dogal gaz 100 m3\n", "text/plain")},
                     follow_redirects=False)
    assert r.status_code == 303


def test_izinsiz_bicim_reddedilir(istemci):
    r = istemci.post("/belgeler/yukle",
                     files={"dosya": ("kotu.exe", b"MZ\x00", "application/exe")},
                     follow_redirects=False)
    assert r.status_code == 303
    assert "hata=bicim" in r.headers["location"]


def test_bos_dosya_reddedilir(istemci):
    r = istemci.post("/belgeler/yukle",
                     files={"dosya": ("bos.txt", b"", "text/plain")},
                     follow_redirects=False)
    assert "hata=bos" in r.headers["location"]


# ------------------------------------------------------------ mükerrer yükleme
def test_ayni_belge_iki_kez_envanteri_sismez(istemci):
    icerik = ("ORNEK FATURA\nOkuma Donemi: 01.09.2027 - 28.09.2027\n"
              "Dogal gaz tuketimi   45 000   m3   333 000,00\n")
    dosya = {"dosya": ("mukerrer.txt", icerik.encode("utf-8"), "text/plain")}
    istemci.post("/belgeler/yukle", files=dosya, follow_redirects=True)
    once = istemci.get("/api/ozet").json()["envanter"]["toplam"]

    r = istemci.post("/belgeler/yukle",
                     files={"dosya": ("mukerrer_kopya.txt",
                                      icerik.encode("utf-8"), "text/plain")},
                     follow_redirects=False)
    assert "uyari=mukerrer" in r.headers["location"]
    sonra = istemci.get("/api/ozet").json()["envanter"]["toplam"]
    assert sonra == pytest.approx(once)


# ---------------------------------------------------------------- açık yönlendirme
def test_dil_degisimi_dis_siteye_yonlendirmez(istemci):
    r = istemci.get("/dil/uz", headers={"referer": "https://kotu-site.example/x"},
                    follow_redirects=False)
    assert r.headers["location"] == "/"
    r2 = istemci.get("/dil/tr", headers={"referer": "http://testserver/urun"},
                     follow_redirects=False)
    assert r2.headers["location"] == "/urun"


# ------------------------------------------------------------------ demo koruma
def test_demo_onaysiz_calismaz(istemci):
    from app import settings_store as A
    db = SessionLocal()
    try:
        A.set_many(db, {"allow_demo_reset": "1"})   # bayrak açıkken bile
        db.commit()
    finally:
        db.close()

    r = istemci.post("/demo", data={}, follow_redirects=False)
    assert r.status_code == 303 and "hata=onay" in r.headers["location"]
    assert istemci.get("/api/ozet").status_code == 200


def test_demo_bayrak_kapaliyken_reddedilir(istemci):
    from app import settings_store as A
    db = SessionLocal()
    try:
        A.set_many(db, {"allow_demo_reset": "0"})
        db.commit()
    finally:
        db.close()
    r = istemci.post("/demo", data={"onay": "EVET"}, follow_redirects=False)
    assert r.status_code == 403
    db = SessionLocal()
    try:
        A.set_many(db, {"allow_demo_reset": "1"})
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------- fiyat satırları
@pytest.mark.parametrize("satir", [
    "Birim Fiyat (Doğal gaz): 7,40 TL/m3",
    "Reaktif enerji   Birim fiyat: 0,45 TL/kWh",
    "Doğal gaz tarife bedeli 12,30",
    "KDV %20 doğal gaz 1 234,00",
])
def test_fiyat_satiri_faaliyet_verisi_sayilmaz(satir):
    assert fiyat_satiri_mi(satir)
    assert _aday_satirlar(satir + "\n") == []


def test_gercek_miktar_satiri_alinir():
    a = _aday_satirlar("Doğal gaz tüketimi   118 000   m3   873 200,00\n")
    assert len(a) == 1 and a[0]["value"] == pytest.approx(118_000.0)


# ------------------------------------------------------------- ülke ve şebeke
def test_ozbekistan_sebeke_faktoru_kullanilir():
    assert F.find_factor_key("Aktif enerji 100 kWh", "UZ") == "elektrik_uz"
    assert F.find_factor_key("Aktif enerji 100 kWh", "TR") == "elektrik_tr"
    tr = calc.hesapla("elektrik_tr", 1000).co2e_kg
    uz = calc.hesapla("elektrik_uz", 1000).co2e_kg
    assert uz > tr


# ------------------------------------------------------ tedarikçi faktör geçişi
def test_tedarikci_degeri_varsayim_faktorunu_degistirir(istemci):
    db = SessionLocal()
    try:
        t = db.query(Supplier).filter(
            Supplier.factor_key == "hurda_celik").first()
        assert t is not None
        sid = t.id
    finally:
        db.close()

    once = istemci.get("/api/ozet").json()["envanter"]["scope3"]
    r = istemci.post(f"/tedarik/{sid}/yanit",
                     data={"deger": "250", "faktor": "hurda_celik"},
                     follow_redirects=False)
    assert r.status_code == 303
    sonra = istemci.get("/api/ozet").json()["envanter"]["scope3"]
    assert sonra < once          # 430 varsayımı yerine 250 gerçek değeri

    csv = istemci.get("/api/envanter.csv").text
    assert "tedarikci" in csv


def test_yakit_faktoru_tedarikci_degeriyle_degistirilemez():
    with pytest.raises(ValueError):
        calc.hesapla("dogalgaz", 100, override_kgco2e_per_unit=10)


def test_negatif_tedarikci_degeri_reddedilir(istemci):
    db = SessionLocal()
    try:
        sid = db.query(Supplier).first().id
    finally:
        db.close()
    r = istemci.post(f"/tedarik/{sid}/yanit",
                     data={"deger": "-5", "faktor": "hurda_celik"},
                     follow_redirects=False)
    assert "hata=deger" in r.headers["location"]


# -------------------------------------------------------- zincir ve tutarlılık
def test_zincirde_alti_ajan_da_calisir(istemci):
    r = istemci.post("/ajanlar/calistir")
    assert r.status_code == 200
    for ad in ("faktor", "faktor_yeniden", "denetim", "uyum", "azaltim",
               "tedarik"):
        assert ad in r.text


def test_reddedilen_satir_envanterden_tamamen_cikar(istemci):
    from app.services import onay_kuyrugu
    db = SessionLocal()
    try:
        kuyruk = onay_kuyrugu(db, 1)
    finally:
        db.close()
    if not kuyruk:
        pytest.skip("onay kuyruğu boş")
    sid = kuyruk[0].id
    once = istemci.get("/api/ozet").json()["envanter"]["toplam"]
    istemci.post(f"/denetim/{sid}/reddet", follow_redirects=False)
    sonra = istemci.get("/api/ozet").json()["envanter"]["toplam"]
    assert sonra <= once
    csv = istemci.get("/api/envanter.csv").text
    assert f"\n{sid};" not in csv      # hayalet satır kalmamalı


def test_rapor_sayisi_sinirlanir(istemci):
    from app.models import Report
    for _ in range(4):
        istemci.post("/ajanlar/calistir")
    db = SessionLocal()
    try:
        assert db.query(Report).count() <= 20
    finally:
        db.close()


def test_tedarikci_hatirlatmasi_her_calismada_tekrarlanmaz(istemci):
    import datetime as dt
    from app.models import AuditEvent
    db = SessionLocal()
    try:
        t = db.query(Supplier).filter(Supplier.status != "yanitladi").first()
        if t is None:
            pytest.skip("bekleyen tedarikçi yok")
        t.requested_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=40)
        t.last_reminder_at = None
        t.reminder_count = 0
        t.status = "hazirlandi"
        db.commit()
        tid = t.id
    finally:
        db.close()

    for _ in range(3):
        istemci.post("/ajanlar/calistir")

    db = SessionLocal()
    try:
        sayi = db.query(AuditEvent).filter(
            AuditEvent.entity == "supplier", AuditEvent.entity_id == tid,
            AuditEvent.action == "tedarik.hatirlatma").count()
        assert sayi == 1
    finally:
        db.close()
