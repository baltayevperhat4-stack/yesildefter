"""Erişim parolası (HTTP Basic) testleri."""

import base64
import os
import tempfile

import pytest

TMP = tempfile.mkdtemp(prefix="yd_parola_")
os.environ["YD_DATA_DIR"] = TMP
os.environ["DATABASE_URL"] = f"sqlite:///{TMP}/parola.db"

from fastapi.testclient import TestClient          # noqa: E402

from app import main as M                          # noqa: E402
from app.models import init_db                     # noqa: E402


@pytest.fixture(scope="module")
def istemci():
    init_db()
    with TestClient(M.app) as c:
        yield c


def _basic(kullanici: str, parola: str) -> dict:
    ham = f"{kullanici}:{parola}".encode("utf-8")
    return {"Authorization": "Basic " + base64.b64encode(ham).decode("ascii")}


@pytest.fixture()
def korumali(monkeypatch):
    monkeypatch.setattr(M, "ACCESS_PASSWORD", "gizli-123")
    monkeypatch.setattr(M, "ACCESS_USER", "jury")


# ------------------------------------------------------- parola tanımsızken
def test_parola_yoksa_sayfa_acik(istemci):
    assert M.ACCESS_PASSWORD == ""          # yerel varsayılan
    assert istemci.get("/").status_code == 200


# -------------------------------------------------------- parola tanımlıyken
def test_parolasiz_istek_reddedilir(istemci, korumali):
    r = istemci.get("/")
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"].startswith("Basic")


def test_dogru_parola_gecer(istemci, korumali):
    r = istemci.get("/", headers=_basic("jury", "gizli-123"))
    assert r.status_code == 200


@pytest.mark.parametrize("kullanici,parola", [
    ("jury", "yanlis"),
    ("baskasi", "gizli-123"),
    ("jury", ""),
    ("", ""),
])
def test_yanlis_bilgi_reddedilir(istemci, korumali, kullanici, parola):
    assert istemci.get("/", headers=_basic(kullanici, parola)).status_code == 401


@pytest.mark.parametrize("baslik", [
    "",
    "Bearer abc",
    "Basic ???",                       # base64 değil
    "Basic " + base64.b64encode(b"iki-nokta-yok").decode(),
    "Basic " + base64.b64encode(b"\xff\xfe").decode(),   # utf-8 değil
])
def test_bozuk_baslik_cokmez(istemci, korumali, baslik):
    r = istemci.get("/", headers={"Authorization": baslik} if baslik else {})
    assert r.status_code == 401


def test_yazma_uclari_da_korunur(istemci, korumali):
    assert istemci.post("/demo").status_code == 401
    assert istemci.get("/ayarlar").status_code == 401
    assert istemci.get("/api/ozet").status_code == 401
    assert istemci.get("/api/envanter.csv").status_code == 401


def test_saglik_ucu_acik_kalir(istemci, korumali):
    """Railway sağlık yoklaması kimlik göndermez; bu uç kapanmamalı."""
    r = istemci.get("/api/saglik")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_statik_dosyalar_acik_kalir(istemci, korumali):
    assert istemci.get("/static/app.css").status_code == 200
