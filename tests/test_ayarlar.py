"""Ayarlar, çok sağlayıcılı LLM katmanı ve istemler için testler."""

import os
import tempfile

import pytest

TMP = tempfile.mkdtemp(prefix="yd_ayar_")
os.environ["YD_DATA_DIR"] = TMP
os.environ["DATABASE_URL"] = f"sqlite:///{TMP}/ayar.db"

from fastapi.testclient import TestClient          # noqa: E402

from app import settings_store as A                # noqa: E402
from app.llm import prompts as P                   # noqa: E402
from app.llm import provider as llm                # noqa: E402
from app.main import app                           # noqa: E402
from app.models import SessionLocal, init_db       # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _tablolar():
    init_db()


@pytest.fixture(scope="module")
def istemci():
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


# ----------------------------------------------------- sağlayıcı tanıma
@pytest.mark.parametrize("anahtar,beklenen", [
    ("sk-ant-api03-xxxx", "anthropic"),
    ("sk-or-v1-xxxx", "openrouter"),
    ("gsk_xxxxxxxx", "groq"),
    ("AIzaSyXXXXXXXX", "google"),
    ("AQ.Ab8RNxxxxxxxxxxxx", "google"),
    ("tgp_v1_xxxx", "together"),
    ("sk-proj-xxxx", "openai"),
    ("sk-xxxx", "openai"),
    ("", "none"),
])
def test_anahtardan_saglayici_taninir(anahtar, beklenen):
    assert llm.tahmin_saglayici(anahtar) == beklenen


def test_google_iki_kimlik_bicimini_de_dener(monkeypatch):
    """AQ. anahtarı 401 verirse Bearer ile bir kez daha denenmeli."""
    import httpx
    cagrilar = []

    class SahteYanit:
        def __init__(self, kod):
            self.status_code = kod
            self.text = "hata"

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("x", request=None, response=self)

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "TAMAM"}]}}]}

    def sahte_post(url, headers=None, json=None, timeout=None):
        cagrilar.append(headers)
        # ilk çağrı reddedilsin, ikincisi geçsin
        return SahteYanit(401 if len(cagrilar) == 1 else 200)

    monkeypatch.setattr(llm.httpx, "post", sahte_post)
    y = {"saglayici": "google", "anahtar": "AQ.Abc", "model": "gemini-x",
         "base": "https://x"}
    assert llm._google(y, "s", "k", 10) == "TAMAM"
    assert len(cagrilar) == 2
    # iki farklı kimlik biçimi denenmiş olmalı
    anahtarlar = [set(h) for h in cagrilar]
    assert any("Authorization" in a for a in anahtarlar)
    assert any("x-goog-api-key" in a for a in anahtarlar)


def test_taban_adres_verilince_uyumlu_moda_gecer():
    assert llm.tahmin_saglayici("herhangi-bir-anahtar",
                                "http://localhost:11434/v1") == "uyumlu"


def test_her_saglayicinin_varsayilan_modeli_var():
    for ad, (model, base) in llm.SAGLAYICILAR.items():
        if ad == "uyumlu":
            continue
        assert model and base.startswith("http"), ad


# ------------------------------------------------------------- ayar katmanı
def test_anahtar_yoksa_sistem_kapali(db):
    y = llm.yapilandirma(db)
    assert y["saglayici"] == "none"
    assert llm.kullanilabilir(db) is False


def test_ayar_yazilir_ve_okunur(db):
    A.set_many(db, {"llm_api_key": "sk-ant-test-123456789012",
                    "llm_provider": "auto"})
    db.commit()
    y = llm.yapilandirma(db)
    assert y["saglayici"] == "anthropic"
    assert y["model"] == "claude-sonnet-4-5"
    assert llm.kullanilabilir(db) is True


def test_anahtar_maskelenir(db):
    deger = A.arayuz_degerleri(db)["llm_api_key"]
    assert "•" in deger
    assert "sk-ant-test-123456789012" not in deger


def test_bos_gizli_alan_mevcut_anahtari_silmez(db):
    A.set_many(db, {"llm_api_key": ""})
    db.commit()
    assert A.get("llm_api_key", db).startswith("sk-ant-test")


def test_maskeyi_geri_gondermek_anahtari_bozmaz(db):
    A.set_many(db, {"llm_api_key": "••••••••••"})
    db.commit()
    assert A.get("llm_api_key", db).startswith("sk-ant-test")


def test_esik_araliga_sikistirilir(db):
    A.set_many(db, {"confidence_threshold": "5"})
    db.commit()
    assert A.esik(db) == 0.99
    A.set_many(db, {"confidence_threshold": "-1"})
    db.commit()
    assert A.esik(db) == 0.50
    A.set_many(db, {"confidence_threshold": "0.85"})
    db.commit()
    assert A.esik(db) == pytest.approx(0.85)


def test_bozuk_sayi_varsayilana_duser(db):
    A.set_many(db, {"cbam_cert_eur": "abc"})
    db.commit()
    assert A.cbam_eur(db) == 75.0


def test_virgullu_sayi_kabul_edilir(db):
    A.set_many(db, {"cbam_cert_eur": "82,5"})
    db.commit()
    assert A.cbam_eur(db) == pytest.approx(82.5)
    A.set_many(db, {"cbam_cert_eur": "75"})
    db.commit()


def test_telegram_izinli_listesi_ayristirilir(db):
    A.set_many(db, {"telegram_allowed_chats": "123, -456 , abc, 789"})
    db.commit()
    assert A.telegram_ayarlari(db)["izinli"] == {123, -456, 789}


def test_bilinmeyen_ayar_yok_sayilir(db):
    A.set_many(db, {"kotu_anahtar": "deger"})
    db.commit()
    assert A.get("kotu_anahtar", db) == ""


def test_anahtar_silinebilir(db):
    A.sil(db, "llm_api_key")
    db.commit()
    assert A.get("llm_api_key", db) == ""
    assert llm.kullanilabilir(db) is False


# ------------------------------------------------------------- arayüz
def test_ayar_sayfasi_acilir(istemci):
    r = istemci.get("/ayarlar")
    assert r.status_code == 200
    assert "API" in r.text


def test_ayar_formu_kaydeder(istemci):
    r = istemci.post("/ayarlar", data={
        "llm_api_key": "sk-ant-form-9999999999",
        "llm_provider": "auto",
        "confidence_threshold": "0.88",
        "cbam_cert_eur": "80",
        "llm_aciklama": "on",
    }, follow_redirects=False)
    assert r.status_code == 303
    s = SessionLocal()
    try:
        assert A.esik(s) == pytest.approx(0.88)
        assert A.cbam_eur(s) == 80.0
        assert A.get_bool("llm_aciklama", s) is True
        # formda işaretlenmeyen kutu kapanmalı
        assert A.get_bool("llm_faktor_onerisi", s) is False
    finally:
        s.close()


def test_sayfada_anahtar_acikta_gosterilmez(istemci):
    r = istemci.get("/ayarlar")
    assert "sk-ant-form-9999999999" not in r.text


def test_baglanti_sinama_hata_verse_de_cokmez(istemci):
    r = istemci.post("/ayarlar/sina")
    assert r.status_code == 200          # gerçek anahtar yok; sayfa yine açılır


def test_anahtar_silme_ucu(istemci):
    r = istemci.post("/ayarlar/anahtar-sil", follow_redirects=False)
    assert r.status_code == 303
    s = SessionLocal()
    try:
        assert A.get("llm_api_key", s) == ""
    finally:
        s.close()


def test_aciklama_ucu_model_yokken_bos_doner(istemci):
    r = istemci.post("/aciklama/envanter")
    assert r.status_code == 200
    assert r.json()["ok"] is False


# ------------------------------------------------------------------ istemler
def test_cikarim_istemi_katalogu_ve_belgeyi_tasir():
    k = P.cikarim_kullanici("Doğal gaz tüketimi 100 m3", "TR")
    assert "dogalgaz" in k and "elektrik_tr" in k
    assert "Doğal gaz tüketimi 100 m3" in k
    assert "Yalnızca JSON" in k


def test_cikarim_istemi_ulkeye_gore_sebeke_secer():
    assert "elektrik_uz" in P.cikarim_kullanici("x", "UZ")
    assert "'elektrik_tr'" in P.cikarim_kullanici("x", "TR")


def test_sistem_istemi_uydurmayi_yasaklar():
    assert "UYDURMA" in P.CIKARIM_SISTEM
    assert "MİKTAR, TUTAR DEĞİLDİR" in P.CIKARIM_SISTEM
    assert "Birim Fiyat" in P.CIKARIM_SISTEM


def test_guven_capalari_istemde_var():
    for capa in ("0,95-0,99", "0,85-0,94", "0,60-0,84", "0,30-0,59"):
        assert capa in P.CIKARIM_SISTEM


def test_aciklama_istemi_hesap_yapmayi_yasaklar():
    assert "Hesap yapma" in P.ACIKLAMA_SISTEM
    k = P.aciklama_kullanici("Toplam: 10 tCO2e", "uz")
    assert "Özbekçe" in k


def test_eposta_istemi_sayi_uydurmayi_yasaklar():
    assert "uydurma" in P.EPOSTA_SISTEM
    k = P.eposta_kullanici("Tesis A", "Tedarikçi B", "Hurda çelik", "ton")
    assert "Tesis A" in k and "Hurda çelik" in k


def test_faktor_istemi_null_secenegi_sunar():
    assert "null" in P.FAKTOR_SISTEM
    assert "insan onayına düşer" in P.FAKTOR_SISTEM


# ------------------------------------------------- JSON ayrıştırma dayanıklılığı
@pytest.mark.parametrize("ham,beklenen_satir", [
    ('{"rows":[{"factor_key":"dogalgaz"}]}', 1),
    ('```json\n{"rows":[{"factor_key":"dogalgaz"}]}\n```', 1),
    ('İşte sonuç:\n{"rows":[{"factor_key":"dogalgaz"}]}\nUmarım yardımcı olur.', 1),
])
def test_model_ciktisi_ayristirilir(monkeypatch, ham, beklenen_satir):
    monkeypatch.setattr(llm, "sor", lambda *a, **k: ham)
    veri = llm.json_sor("s", "k")
    assert veri is not None and len(veri["rows"]) == beklenen_satir


@pytest.mark.parametrize("ham", ["", "hiç JSON yok", "[1,2,3]", None])
def test_bozuk_model_ciktisi_none_doner(monkeypatch, ham):
    monkeypatch.setattr(llm, "sor", lambda *a, **k: ham)
    assert llm.json_sor("s", "k") is None


def test_model_satiri_dogrulanir():
    from app.agents.document_agent import _satir_temizle
    assert _satir_temizle({"factor_key": "yok_boyle", "value": 5}) is None
    assert _satir_temizle({"factor_key": "dogalgaz", "value": "abc"}) is None
    assert _satir_temizle({"factor_key": "dogalgaz", "value": -5}) is None
    t = _satir_temizle({"factor_key": "dogalgaz", "value": 100,
                        "confidence": 5})
    assert t is not None and t["confidence"] == 0.99
