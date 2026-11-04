"""Çeviri bütünlüğü testleri.

Amaç: arayüzü başka bir dile çevirdiğinde sayfanın yarısının Türkçe kalmaması.
Bu, elle gözden kaçan bir kusurdu; artık test tutuyor.
"""

import os
import re
import tempfile

import pytest

TMP = tempfile.mkdtemp(prefix="yd_dil_")
os.environ["YD_DATA_DIR"] = TMP
os.environ["DATABASE_URL"] = f"sqlite:///{TMP}/dil.db"

from fastapi.testclient import TestClient              # noqa: E402

from app.config import LANGS                           # noqa: E402
from app.core.factors import all_factors               # noqa: E402
from app.i18n import S                                 # noqa: E402
from app.main import app                               # noqa: E402
from app.messages import (ETIKET, FAKTOR_ADI, KAYNAK_ADI, MESAJ,
                          ceviri_kontrol, etiket, faktor_adi,
                          mesaj)                        # noqa: E402
from app.models import init_db                          # noqa: E402
from seed.demo import yukle                             # noqa: E402

SAYFALAR = ["/", "/belgeler", "/denetim", "/urun", "/azaltim", "/tedarik",
            "/ajanlar", "/faktorler", "/ayarlar"]

# Türkçe dışı dillerde sayfada görünmemesi gereken izler. Belgeden gelen ham
# fatura metni (source_line) bu denetimden çıkarılır — o belgenin kendi dilidir.
TURKCE_IZ = [
    "satır hesaplandı", "onay bekliyor", "bulunamadı", "kullanıyor",
    "Varsayım faktörü", "Doğal gaz", "Taş kömürü", "Çatı güneş",
    "atık ısı", "Basınçlı hava", "değiştirilmelidir", "Tesis bulunamadı",
    "tedarikçi;", "önlem,", "kapsam dışı",
]
HAM_BELGE = re.compile(
    r"(Doğal gaz tüketimi[^<]*|Aktif enerji[^<]*|Hurda çelik[^<]*"
    r"|Karayolu taşıma\s+[\d ]+[^<]*|Motorin[^<]*)")


@pytest.fixture(scope="module")
def istemci():
    init_db()
    yukle(sifirla=True)
    with TestClient(app) as c:
        c.post("/ajanlar/calistir")
        yield c


# ------------------------------------------------------- sözlük bütünlüğü
def test_arayuz_sozlugu_her_dilde_tam():
    tr = set(S["tr"])
    for d in LANGS:
        eksik = tr - set(S[d])
        assert not eksik, f"{d} dilinde eksik anahtar: {sorted(eksik)[:10]}"


def test_dinamik_mesajlar_her_dilde_tam():
    eksik = ceviri_kontrol()
    assert not eksik, f"eksik çeviri: {eksik[:10]}"


def test_her_faktorun_adi_her_dilde_var():
    for f in all_factors():
        assert f["key"] in FAKTOR_ADI, f"{f['key']} çevirisiz"
        for d in LANGS:
            assert FAKTOR_ADI[f["key"]].get(d), f"{f['key']}/{d}"


def test_her_faktor_duzeyi_cevrilir():
    for tier in ("ipcc", "ulusal", "varsayim", "tedarikci"):
        assert tier in KAYNAK_ADI
        for d in LANGS:
            assert KAYNAK_ADI[tier].get(d)


def test_bilinmeyen_kod_sayfayi_bozmaz():
    assert mesaj("uz", "yok.boyle.kod") == "yok.boyle.kod"
    assert etiket("uz", "bilinmeyen_durum") == "bilinmeyen_durum"
    # eksik parametre de patlamamalı
    assert mesaj("uz", "bulgu.aykiri_deger") != ""


def test_mesaj_parametreleri_yerine_oturur():
    m = mesaj("en", "bulgu.onay_bekliyor", guven=55, esik=90, satir="X")
    assert "55" in m and "90" in m and "X" in m
    assert "{" not in m


def test_her_mesaj_ayni_parametreleri_kullanir():
    """Bir dilde {guven} varsa hepsinde olmalı; yoksa o dilde bilgi kaybolur."""
    for code, diller in MESAJ.items():
        alanlar = {d: set(re.findall(r"\{(\w+)\}", m)) for d, m in diller.items()}
        tr_alan = alanlar.get("tr", set())
        for d, a in alanlar.items():
            assert a == tr_alan, f"{code}: {d} alanları {a} != tr {tr_alan}"


# ---------------------------------------------------------- sayfa denetimi
@pytest.mark.parametrize("lang", [d for d in LANGS if d != "tr"])
@pytest.mark.parametrize("yol", SAYFALAR)
def test_sayfada_turkce_kalinti_yok(istemci, lang, yol):
    istemci.cookies.set("yd_lang", lang)
    r = istemci.get(yol)
    assert r.status_code == 200
    govde = HAM_BELGE.sub("", r.text)       # ham fatura metni hariç
    kalinti = [iz for iz in TURKCE_IZ if iz in govde]
    assert not kalinti, f"{yol} ({lang}) Türkçe kalıntı: {kalinti}"


@pytest.mark.parametrize("lang", LANGS)
def test_tum_sayfalar_her_dilde_acilir(istemci, lang):
    istemci.cookies.set("yd_lang", lang)
    for yol in SAYFALAR + ["/iz", "/belgeler/1"]:
        assert istemci.get(yol).status_code == 200, f"{yol} / {lang}"


# ------------------------------------------------------------------- tema
@pytest.mark.parametrize("kod,beklenen", [("acik", "acik"), ("koyu", "koyu"),
                                          ("oto", "oto"), ("bozuk", "oto")])
def test_tema_degisimi(istemci, kod, beklenen):
    r = istemci.get(f"/tema/{kod}", follow_redirects=False)
    assert r.status_code == 303
    assert r.cookies.get("yd_tema") == beklenen


def test_tema_sayfaya_islenir(istemci):
    r = istemci.get("/", headers={"Cookie": "yd_tema=acik"})
    assert 'data-tema="acik"' in r.text
    r2 = istemci.get("/", headers={"Cookie": "yd_tema=koyu"})
    assert 'data-tema="koyu"' in r2.text


def test_acik_tema_css_tanimli():
    from pathlib import Path
    css = (Path(__file__).parent.parent / "app" / "web" / "static"
           / "app.css").read_text(encoding="utf-8")
    assert ':root[data-tema="acik"]' in css
    assert "prefers-color-scheme: light" in css
