"""YeşilDefter — FastAPI uygulaması (web arayüzü + JSON API)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import services as S
from . import settings_store as A
from .agents import orchestrator
from .agents.document_agent import metin_oku
from .agents.base import iz_birak
from .agents.supplier_agent import yanit_kaydet
from .config import (ACCESS_PASSWORD, ACCESS_USER, ALLOW_DEMO_RESET,
                     ALLOWED_UPLOAD_EXT, APP_NAME, APP_VERSION,
                     CONFIDENCE_THRESHOLD, LANGS, MAX_AD, MAX_DOSYA_ADI,
                     MAX_REPORTS, MAX_SEKTOR, MAX_UPLOAD_BYTES, UPLOAD_DIR)
from .core import factors as F
from .core.util import sonlu, temiz_metin
from .i18n import DIL_ADLARI, normalize, sozluk
from .messages import etiket, faktor_adi, kaynak_adi, mesaj
from .llm import provider as llm
from .models import (Activity, Document, Facility, Report,
                     get_session, init_db)

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "web" / "templates"))


def _sayi(deger, basamak: int = 0) -> str:
    """1234567.8 -> '1 234 568' (ince boşluklu binlik, Türkçe ondalık)."""
    try:
        d = float(deger)
    except (TypeError, ValueError):
        return "—"
    s = f"{d:,.{basamak}f}"
    return s.replace(",", " ").replace(".", ",")


def _yuzde(deger, basamak: int = 0) -> str:
    try:
        return f"%{float(deger):.{basamak}f}".replace(".", ",")
    except (TypeError, ValueError):
        return "—"


templates.env.filters["sayi"] = _sayi
templates.env.filters["yuzde"] = _yuzde

@asynccontextmanager
async def _yasam(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=_yasam)
app.mount("/static", StaticFiles(directory=str(BASE / "web" / "static")),
          name="static")


# ------------------------------------------------------------ erişim koruması
# YD_PAROL tanımlıysa tüm uygulama HTTP Basic ile korunur. Sağlık ucu ve statik
# dosyalar dışarıda bırakılır: Railway sağlık yoklaması kimlik göndermez.
ACIK_YOLLAR = ("/api/saglik", "/static/")


def _kimlik_dogru(baslik: str) -> bool:
    """Authorization başlığını doğrular. Zamanlama sızıntısına karşı sabit süre."""
    if not baslik.lower().startswith("basic "):
        return False
    try:
        ham = base64.b64decode(baslik.split(" ", 1)[1], validate=True)
        kullanici, ayrac, parola = ham.decode("utf-8").partition(":")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    if not ayrac:
        return False
    # İki karşılaştırma da her zaman çalışsın; "and" kısa devre yapmasın.
    k = secrets.compare_digest(kullanici, ACCESS_USER)
    p = secrets.compare_digest(parola, ACCESS_PASSWORD)
    return k and p


@app.middleware("http")
async def parola_korumasi(request: Request, call_next):
    if ACCESS_PASSWORD and not request.url.path.startswith(ACIK_YOLLAR):
        if not _kimlik_dogru(request.headers.get("authorization", "")):
            return Response(
                content="Yetkisiz erişim.", status_code=401,
                media_type="text/plain; charset=utf-8",
                headers={"WWW-Authenticate": 'Basic realm="YesilDefter"'})
    return await call_next(request)


# --------------------------------------------------------------- yardımcılar
TEMALAR = ("oto", "acik", "koyu")


def tema(request: Request) -> str:
    """Seçili tema: oto | acik | koyu."""
    t = request.cookies.get("yd_tema")
    return t if t in TEMALAR else "oto"


def dil(request: Request) -> str:
    q = request.query_params.get("lang")
    if q in LANGS:
        return q
    return normalize(request.cookies.get("yd_lang"))


GUVENLI_YOL = re.compile(r"^/[A-Za-z0-9_\-/]*$")


def guvenli_hedef(request: Request) -> str:
    """Referer başlığından yalnızca kendi sitemizdeki yolu kabul eder.

    Başlık istemciden gelir; doğrudan yönlendirme hedefi yapılırsa saldırgan
    kullanıcıyı dış bir siteye taşıyabilir (açık yönlendirme).
    """
    ham = request.headers.get("referer") or "/"
    try:
        from urllib.parse import urlparse
        u = urlparse(ham)
    except Exception:
        return "/"
    if u.scheme or u.netloc:
        if u.netloc and u.netloc != request.url.netloc:
            return "/"
    yol = u.path or "/"
    return yol if GUVENLI_YOL.match(yol) else "/"


def guvenli_dosya_adi(ham: str | None) -> str:
    """Yüklenen dosya adını güvenli bir ada indirger.

    `..`, `/` ve boş ad gibi durumlar dizine yazmaya kalkışıp çökmeye yol açar;
    bu yüzden her zaman kullanılabilir bir ad döndürürüz.
    """
    ad = temiz_metin(Path(ham or "").name, MAX_DOSYA_ADI)
    ad = re.sub(r"[^A-Za-z0-9._\- ]+", "_", ad).strip(" ._")
    if not ad or ad in (".", ".."):
        ad = "belge.txt"
    if not Path(ad).suffix:
        ad += ".txt"
    return ad


def ctx(request: Request, db: Session, **ek) -> dict:
    lang = dil(request)
    tesis = S.aktif_tesis(db)
    bekleyen_sayi = S.bekleyen_adet(db, tesis.id) if tesis else 0
    temel = {
        "bekleyen_sayi": bekleyen_sayi,
        # dinamik metinleri kullanıcının dilinde kuran yardımcılar
        "m": lambda kod, **p: mesaj(lang, kod, **p),
        "et": lambda anahtar: etiket(lang, anahtar),
        "fad": lambda key, vars="": faktor_adi(lang, key, vars),
        "kad": lambda tier, vars="": kaynak_adi(lang, tier, vars),
        "request": request,
        "L": sozluk(lang),
        "lang": lang,
        "langs": [(k, DIL_ADLARI[k]) for k in LANGS],
        "tesis": tesis,
        "app_version": APP_VERSION,
        "factor_version": F.FACTOR_SET_VERSION,
        "llm_var": llm.kullanilabilir(db),
        "esik": A.esik(db),
        "yol": request.url.path,
        "tema": tema(request),
        "temalar": TEMALAR,
    }
    temel.update(ek)
    return temel


def _tesis_yoksa_yonlendir(tesis) -> RedirectResponse | None:
    if tesis is None:
        return RedirectResponse("/kurulum", status_code=303)
    return None


# ------------------------------------------------------------------- sayfalar
@app.get("/dil/{kod}")
def dil_degistir(kod: str, request: Request):
    cevap = RedirectResponse(guvenli_hedef(request), status_code=303)
    cevap.set_cookie("yd_lang", normalize(kod), max_age=60 * 60 * 24 * 365,
                     samesite="lax")
    return cevap


@app.get("/tema/{kod}")
def tema_degistir(kod: str, request: Request):
    cevap = RedirectResponse(guvenli_hedef(request), status_code=303)
    cevap.set_cookie("yd_tema", kod if kod in TEMALAR else "oto",
                     max_age=60 * 60 * 24 * 365, samesite="lax")
    return cevap


@app.get("/", response_class=HTMLResponse)
def pano(request: Request, db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if (y := _tesis_yoksa_yonlendir(tesis)) is not None:
        return y
    veri = S.pano(db, tesis.id)
    return templates.TemplateResponse(request, "pano.html", ctx(request, db, p=veri))


@app.get("/kurulum", response_class=HTMLResponse)
def kurulum(request: Request, db: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "kurulum.html", ctx(request, db))


@app.post("/kurulum")
def kurulum_kaydet(request: Request, ad: str = Form(...), sektor: str = Form(""),
                   ulke: str = Form("TR"), uretim: float = Form(0.0),
                   ihracat: float = Form(0.0), yil: int = Form(2027),
                   db: Session = Depends(get_session)):
    # Tek tesisli sürüm: mevcut tesis varsa ikincisi oluşturulmaz, çünkü
    # tüm sayfalar ilk tesisi gösterir ve ikinci kayıt sessizce yok sayılırdı.
    if S.aktif_tesis(db) is not None:
        return RedirectResponse("/", status_code=303)

    ad = temiz_metin(ad, MAX_AD)
    if not ad:
        return RedirectResponse("/kurulum?hata=ad", status_code=303)
    sektor = temiz_metin(sektor, MAX_SEKTOR)
    ulke = temiz_metin(ulke, 2).upper() or "TR"
    try:
        uretim = sonlu(uretim, "Üretim")
        ihracat = sonlu(ihracat, "İhracat")
        yil = int(yil)
    except (ValueError, TypeError):
        return RedirectResponse("/kurulum?hata=sayi", status_code=303)
    if uretim < 0 or ihracat < 0 or not (2000 <= yil <= 2100):
        return RedirectResponse("/kurulum?hata=aralik", status_code=303)

    t = Facility(name=ad, sector=sektor, country=ulke, production_ton=uretim,
                 export_ton_eu=ihracat, year=yil)
    db.add(t)
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/demo")
def demo_yukle(onay: str = Form("")):
    # Bu uç nokta TÜM veri tabanını siler. Üretimde YD_ALLOW_DEMO_RESET=0
    # ile kapatılır; açıkken de açık onay ister.
    if not A.demo_sifirlama_acik():
        return JSONResponse({"hata": "demo sıfırlama kapalı"}, status_code=403)
    if onay.strip().upper() not in ("EVET", "YES", "HA"):
        return RedirectResponse("/kurulum?hata=onay", status_code=303)
    from seed.demo import yukle
    yukle(sifirla=True)
    return RedirectResponse("/", status_code=303)


@app.get("/belgeler", response_class=HTMLResponse)
def belgeler(request: Request, db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if (y := _tesis_yoksa_yonlendir(tesis)) is not None:
        return y
    return templates.TemplateResponse(
         request, "belgeler.html", ctx(request, db, liste=S.belgeler(db, tesis.id)))


@app.post("/belgeler/yukle")
async def belge_yukle(request: Request, dosya: UploadFile = File(...),
                      db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if tesis is None:
        return RedirectResponse("/kurulum", status_code=303)

    ad = guvenli_dosya_adi(dosya.filename)
    if Path(ad).suffix.lower() not in ALLOWED_UPLOAD_EXT:
        return RedirectResponse("/belgeler?hata=bicim", status_code=303)

    icerik = await dosya.read(MAX_UPLOAD_BYTES + 1)
    if len(icerik) > MAX_UPLOAD_BYTES:
        return RedirectResponse("/belgeler?hata=boyut", status_code=303)
    if not icerik:
        return RedirectResponse("/belgeler?hata=bos", status_code=303)

    ozet = hashlib.sha256(icerik).hexdigest()
    mevcut = db.scalar(select(Document).where(
        Document.facility_id == tesis.id, Document.content_hash == ozet))
    if mevcut is not None:
        # Aynı belgenin ikinci kez işlenmesi envanteri şişirir.
        return RedirectResponse(f"/belgeler/{mevcut.id}?uyari=mukerrer",
                                status_code=303)

    hedef = UPLOAD_DIR / ad
    sayac = 1
    while hedef.exists():
        hedef = UPLOAD_DIR / f"{Path(ad).stem}_{sayac}{Path(ad).suffix}"
        sayac += 1
    hedef.write_bytes(icerik)

    belge = Document(facility_id=tesis.id, filename=hedef.name,
                     raw_text=metin_oku(hedef), content_hash=ozet)
    db.add(belge)
    db.flush()
    orchestrator.belge_isle(db, belge.id)
    db.commit()
    orchestrator.zinciri_calistir(db, tesis.id)
    S.raporlari_buda(db, tesis.id, MAX_REPORTS)
    return RedirectResponse(f"/belgeler/{belge.id}", status_code=303)


@app.get("/belgeler/{belge_id}", response_class=HTMLResponse)
def belge_detay(belge_id: int, request: Request,
                db: Session = Depends(get_session)):
    d = S.belge_detay(db, belge_id)
    if d is None:
        return RedirectResponse("/belgeler", status_code=303)
    return templates.TemplateResponse(request, "belge.html", ctx(request, db, **d))


@app.get("/denetim", response_class=HTMLResponse)
def denetim(request: Request, db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if (y := _tesis_yoksa_yonlendir(tesis)) is not None:
        return y
    return templates.TemplateResponse(request, "denetim.html", ctx(
        request, db, kuyruk=S.onay_kuyrugu(db, tesis.id),
        bulgular=S.bulgular(db, tesis.id)))


@app.post("/denetim/{activity_id}/{karar}")
def onay_karari(activity_id: int, karar: str,
                db: Session = Depends(get_session)):
    a = db.get(Activity, activity_id)
    if a is not None and karar in ("onayla", "reddet"):
        a.status = "onayli" if karar == "onayla" else "reddedildi"
        db.commit()
        tesis_id = a.document.facility_id
        orchestrator.zinciri_calistir(db, tesis_id)
        S.raporlari_buda(db, tesis_id, MAX_REPORTS)
    return RedirectResponse("/denetim", status_code=303)


@app.post("/denetim/bulgu/{finding_id}/kapat")
def bulgu_kapat(finding_id: int, db: Session = Depends(get_session)):
    """Bulguyu çözülmüş olarak işaretler; denetim izine yazılır."""
    from .models import Finding
    b = db.get(Finding, finding_id)
    if b is not None:
        b.resolved = 1
        iz_birak(db, "finding", b.id, "denetim.bulgu_kapatildi",
                 {"kod": b.code}, actor="kullanici")
        db.commit()
    return RedirectResponse("/denetim", status_code=303)


@app.get("/urun", response_class=HTMLResponse)
def urun(request: Request, db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if (y := _tesis_yoksa_yonlendir(tesis)) is not None:
        return y
    return templates.TemplateResponse(request, "urun.html", ctx(
        request, db, p=S.pano(db, tesis.id), rapor=S.son_rapor(db, tesis.id)))


@app.get("/azaltim", response_class=HTMLResponse)
def azaltim(request: Request, db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if (y := _tesis_yoksa_yonlendir(tesis)) is not None:
        return y
    onlemler = S.olcumler(db, tesis.id)
    toplam = {
        "tco2e": round(sum(m.tco2e_year for m in onlemler), 2),
        "capex": round(sum(m.capex_try for m in onlemler), 0),
        "tasarruf": round(sum(m.saving_try_year for m in onlemler), 0),
    }
    toplam["geri_odeme"] = (round(toplam["capex"] / toplam["tasarruf"], 2)
                            if toplam["tasarruf"] else 0.0)
    return templates.TemplateResponse(request, "azaltim.html", ctx(
        request, db, onlemler=onlemler, toplam=toplam,
        p=S.pano(db, tesis.id)))


@app.get("/tedarik", response_class=HTMLResponse)
def tedarik(request: Request, db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if (y := _tesis_yoksa_yonlendir(tesis)) is not None:
        return y
    return templates.TemplateResponse(request, "tedarik.html", ctx(
        request, db, liste=S.tedarikciler(db, tesis.id),
        kapsam3=F.factors_for_scope(3)))


@app.post("/tedarik/{supplier_id}/yanit")
def tedarik_yanit(supplier_id: int, deger: float = Form(...),
                  faktor: str = Form(""),
                  db: Session = Depends(get_session)):
    try:
        yanit_kaydet(db, supplier_id, deger, temiz_metin(faktor, 60) or None)
    except ValueError:
        return RedirectResponse("/tedarik?hata=deger", status_code=303)
    db.commit()
    # Tedarikçi gerçek değeri geldi: hesaplar bu değerle yeniden yürütülür.
    tesis = S.aktif_tesis(db)
    if tesis is not None:
        orchestrator.zinciri_calistir(db, tesis.id)
        S.raporlari_buda(db, tesis.id, MAX_REPORTS)
    return RedirectResponse("/tedarik", status_code=303)


@app.get("/ajanlar", response_class=HTMLResponse)
def ajanlar(request: Request, db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if (y := _tesis_yoksa_yonlendir(tesis)) is not None:
        return y
    return templates.TemplateResponse(request, "ajanlar.html", ctx(
        request, db, ajanlar=orchestrator.ajan_listesi(),
        sonuclar=None, p=S.pano(db, tesis.id)))


@app.post("/ajanlar/calistir", response_class=HTMLResponse)
def ajan_calistir(request: Request, db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if (y := _tesis_yoksa_yonlendir(tesis)) is not None:
        return y
    sonuclar = orchestrator.zinciri_calistir(db, tesis.id)
    S.raporlari_buda(db, tesis.id, MAX_REPORTS)
    return templates.TemplateResponse(request, "ajanlar.html", ctx(
        request, db, ajanlar=orchestrator.ajan_listesi(),
        sonuclar=sonuclar, p=S.pano(db, tesis.id)))


# ------------------------------------------------------------------ ayarlar
@app.get("/ayarlar", response_class=HTMLResponse)
def ayarlar(request: Request, db: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "ayarlar.html", ctx(
        request, db,
        degerler=A.arayuz_degerleri(db),
        kaynaklar={k: A.kaynak(db, k) for k in A.SEMA},
        llm_durum=llm.durum(db),
        saglayicilar=sorted(llm.SAGLAYICILAR),
        test=None, kayit=request.query_params.get("kayit")))


@app.post("/ayarlar", response_class=HTMLResponse)
async def ayarlar_kaydet(request: Request, db: Session = Depends(get_session)):
    form = await request.form()
    gelen = {k: str(form.get(k, "")) for k in A.SEMA if k in form}
    # onay kutuları: işaretli değilse form'a hiç gelmez
    for bayrak in ("smtp_tls", "allow_demo_reset", "llm_faktor_onerisi",
                   "llm_aciklama", "llm_eposta_taslagi"):
        gelen[bayrak] = "1" if form.get(bayrak) else "0"
    A.set_many(db, gelen)
    iz_birak(db, "setting", None, "ayar.guncellendi",
             {"alanlar": sorted(k for k in gelen if k not in A.GIZLI)},
             actor="kullanici")
    db.commit()
    return RedirectResponse("/ayarlar?kayit=1", status_code=303)


@app.post("/ayarlar/sina", response_class=HTMLResponse)
def ayarlar_sina(request: Request, db: Session = Depends(get_session)):
    sonuc = llm.baglanti_testi(db)
    iz_birak(db, "setting", None, "ayar.baglanti_testi",
             {"ok": sonuc.get("ok"), "saglayici": sonuc.get("saglayici")},
             actor="kullanici")
    db.commit()
    return templates.TemplateResponse(request, "ayarlar.html", ctx(
        request, db,
        degerler=A.arayuz_degerleri(db),
        kaynaklar={k: A.kaynak(db, k) for k in A.SEMA},
        llm_durum=llm.durum(db),
        saglayicilar=sorted(llm.SAGLAYICILAR),
        test=sonuc, kayit=None))


@app.post("/ayarlar/anahtar-sil")
def anahtar_sil(db: Session = Depends(get_session)):
    A.sil(db, "llm_api_key")
    iz_birak(db, "setting", None, "ayar.anahtar_silindi", {}, actor="kullanici")
    db.commit()
    return RedirectResponse("/ayarlar?kayit=silindi", status_code=303)


# ------------------------------------------------------------- AI açıklama
@app.post("/aciklama/satir/{activity_id}")
def aciklama_satir(activity_id: int, request: Request,
                   db: Session = Depends(get_session)):
    from .llm.explain import satir_acikla
    metin = satir_acikla(db, activity_id, dil(request))
    return {"ok": metin is not None, "metin": metin or ""}


@app.post("/aciklama/bulgu/{finding_id}")
def aciklama_bulgu(finding_id: int, request: Request,
                   db: Session = Depends(get_session)):
    from .llm.explain import bulgu_acikla
    metin = bulgu_acikla(db, finding_id, dil(request))
    return {"ok": metin is not None, "metin": metin or ""}


@app.post("/aciklama/envanter")
def aciklama_envanter(request: Request, db: Session = Depends(get_session)):
    from .llm.explain import envanter_acikla
    tesis = S.aktif_tesis(db)
    if tesis is None:
        return {"ok": False, "metin": ""}
    metin = envanter_acikla(db, S.pano(db, tesis.id), dil(request))
    return {"ok": metin is not None, "metin": metin or ""}


@app.get("/faktorler", response_class=HTMLResponse)
def faktorler(request: Request, db: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "faktorler.html", ctx(
        request, db, faktorler=F.all_factors()))


@app.get("/iz", response_class=HTMLResponse)
def iz(request: Request, db: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "iz.html", ctx(
        request, db, kayitlar=S.iz_kayitlari(db)))


# ----------------------------------------------------------------------- API
@app.get("/api/saglik")
def saglik():
    return {"ok": True, "app": APP_NAME, "version": APP_VERSION,
            "faktor_surumu": F.FACTOR_SET_VERSION,
            "llm": llm.aktif_saglayici()}


@app.get("/api/ozet")
def api_ozet(db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if tesis is None:
        return JSONResponse({"hata": "tesis yok"}, status_code=404)
    p = S.pano(db, tesis.id)
    return {
        "tesis": {"id": tesis.id, "ad": tesis.name, "yil": tesis.year},
        "envanter": p["envanter"] and {
            k: p["envanter"][k] for k in ("scope1", "scope2", "scope3", "toplam")},
        "gomulu": p["gomulu"], "kacinilan": p["kacinilan"],
        "onay_bekleyen": p["bekleyen"], "bulgu": p["bulgu_sayi"],
        "azaltim_tco2e": p["azaltim_tco2e"],
        "faktor_surumu": p["factor_version"],
    }


@app.get("/api/rapor")
def api_rapor(db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if tesis is None:
        return JSONResponse({"hata": "tesis yok"}, status_code=404)
    r = S.son_rapor(db, tesis.id)
    if r is None:
        return JSONResponse({"hata": "rapor yok"}, status_code=404)
    return r.payload


@app.get("/api/envanter.csv", response_class=PlainTextResponse)
def api_envanter_csv(db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if tesis is None:
        return PlainTextResponse("tesis yok", status_code=404)
    return Response(S.envanter_csv(db, tesis.id), media_type="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=envanter.csv"})


@app.get("/api/cbam.csv", response_class=PlainTextResponse)
def api_cbam_csv(db: Session = Depends(get_session)):
    tesis = S.aktif_tesis(db)
    if tesis is None:
        return PlainTextResponse("tesis yok", status_code=404)
    return Response(S.cbam_csv(db, tesis.id), media_type="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=cbam_veri_seti.csv"})


@app.get("/api/rapor.xlsx")
def api_rapor_xlsx(db: Session = Depends(get_session)):
    from .core import report
    tesis = S.aktif_tesis(db)
    if tesis is None:
        return JSONResponse({"hata": "tesis yok"}, status_code=404)
    return Response(
        report.xlsx(db, tesis.id),
        media_type="application/vnd.openxmlformats-officedocument."
                   "spreadsheetml.sheet",
        headers={"Content-Disposition":
                 "attachment; filename=yesildefter_rapor.xlsx"})


@app.get("/api/rapor.pdf")
def api_rapor_pdf(db: Session = Depends(get_session)):
    from .core import report
    tesis = S.aktif_tesis(db)
    if tesis is None:
        return JSONResponse({"hata": "tesis yok"}, status_code=404)
    return Response(report.pdf(db, tesis.id), media_type="application/pdf",
                    headers={"Content-Disposition":
                             "inline; filename=yesildefter_rapor.pdf"})


@app.get("/api/faktorler")
def api_faktorler():
    return {"surum": F.FACTOR_SET_VERSION, "faktorler": F.all_factors()}
