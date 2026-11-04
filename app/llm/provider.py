"""Dil modeli katmanı — birden çok sağlayıcı, tek arayüz.

Hangi anahtar girilirse girilsin çalışması hedeflenir: anahtarın biçiminden
sağlayıcı tahmin edilir, tahmin tutmazsa kullanıcı ayar sayfasından elle
seçebilir. OpenAI uyumlu uç noktalar (Groq, OpenRouter, DeepSeek, Together,
yerel Ollama/LM Studio) `base_url` ile desteklenir.

Tasarım kararı değişmedi: sistem dil modeli OLMADAN da eksiksiz çalışır.
Anahtar yoksa çağrılar None döner ve çağıran taraf kural tabanlı yola düşer.
"""

from __future__ import annotations

import json
import random
import re
import time
from typing import Dict, Optional, Tuple

import httpx

from .. import settings_store as A

# sağlayıcı -> (varsayılan model, varsayılan taban adres)
SAGLAYICILAR: Dict[str, Tuple[str, str]] = {
    "anthropic":  ("claude-sonnet-4-5", "https://api.anthropic.com"),
    "openai":     ("gpt-4o-mini", "https://api.openai.com/v1"),
    # "…-latest" takma adı sürüm emekliye ayrılınca da çalışmayı sürdürür;
    # ağır düşünen modeller sınama çağrısında zaman aşımına uğruyordu.
    "google":     ("gemini-flash-lite-latest",
                   "https://generativelanguage.googleapis.com/v1beta"),
    "groq":       ("llama-3.3-70b-versatile", "https://api.groq.com/openai/v1"),
    "openrouter": ("anthropic/claude-3.5-sonnet", "https://openrouter.ai/api/v1"),
    "deepseek":   ("deepseek-chat", "https://api.deepseek.com/v1"),
    "mistral":    ("mistral-small-latest", "https://api.mistral.ai/v1"),
    "together":   ("meta-llama/Llama-3.3-70B-Instruct-Turbo",
                   "https://api.together.xyz/v1"),
    "uyumlu":     ("", ""),     # OpenAI uyumlu, taban adresi kullanıcı verir
}

# anahtarın biçiminden sağlayıcı tahmini — uzun önekler önce denenir
IMZALAR = [
    ("anthropic",  re.compile(r"^sk-ant-")),
    ("openrouter", re.compile(r"^sk-or-")),
    ("groq",       re.compile(r"^gsk_")),
    # Google iki biçim veriyor: eski "AIza…" ve yeni "AQ.…" (Authentication Key)
    ("google",     re.compile(r"^(AIza|AQ\.)")),
    ("together",   re.compile(r"^(tgp_|together_)")),
    ("openai",     re.compile(r"^sk-")),
]

ZAMAN_ASIMI = 90.0

# Geçici sunucu hataları: model aşırı yüklü (503), istek sınırı (429),
# ağ geçidi hatası (502/504). Bunlarda kısa bir bekleyip yeniden denemek
# kullanıcıyı düğmeye tekrar bastırmaktan iyidir.
GECICI_KODLAR = (429, 500, 502, 503, 504)
YENIDEN_DENEME = 3


# ---------------------------------------------------------------- yapılandırma
def tahmin_saglayici(anahtar: str, base_url: str = "") -> str:
    """Anahtarın biçiminden sağlayıcıyı tahmin eder."""
    a = (anahtar or "").strip()
    if base_url.strip():
        return "uyumlu"
    for ad, kalip in IMZALAR:
        if kalip.match(a):
            return ad
    return "openai" if a else "none"


def yapilandirma(db=None) -> dict:
    """Geçerli LLM ayarları: sağlayıcı, anahtar, model, taban adres."""
    anahtar = A.get("llm_api_key", db).strip()
    secim = (A.get("llm_provider", db) or "auto").strip().lower()
    base = A.get("llm_base_url", db).strip()
    model = A.get("llm_model", db).strip()

    if secim in ("none", "kapali"):
        return {"saglayici": "none", "anahtar": "", "model": "", "base": "",
                "neden": "ayarlarda kapatıldı"}
    if not anahtar and secim != "uyumlu":
        return {"saglayici": "none", "anahtar": "", "model": "", "base": "",
                "neden": "API anahtarı girilmemiş"}

    saglayici = tahmin_saglayici(anahtar, base) if secim == "auto" else secim
    if saglayici not in SAGLAYICILAR:
        saglayici = "openai"

    v_model, v_base = SAGLAYICILAR[saglayici]
    return {
        "saglayici": saglayici,
        "anahtar": anahtar,
        "model": model or v_model,
        "base": (base or v_base).rstrip("/"),
        "neden": "",
    }


def aktif_saglayici(db=None) -> str:
    return yapilandirma(db)["saglayici"]


def kullanilabilir(db=None) -> bool:
    y = yapilandirma(db)
    return y["saglayici"] != "none" and bool(y["base"])


def durum(db=None) -> dict:
    """Ayar sayfasında gösterilecek özet."""
    y = yapilandirma(db)
    return {
        "acik": y["saglayici"] != "none",
        "saglayici": y["saglayici"],
        "model": y["model"],
        "base": y["base"],
        "neden": y["neden"],
    }


# ------------------------------------------------------------------- çağrılar
def _anthropic(y: dict, sistem: str, kullanici: str, max_tokens: int) -> str:
    r = httpx.post(
        f"{y['base']}/v1/messages",
        headers={"x-api-key": y["anahtar"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": y["model"], "max_tokens": max_tokens, "system": sistem,
              "messages": [{"role": "user", "content": kullanici}]},
        timeout=ZAMAN_ASIMI)
    r.raise_for_status()
    return "".join(p.get("text", "") for p in r.json().get("content", []))


def _openai_uyumlu(y: dict, sistem: str, kullanici: str, max_tokens: int) -> str:
    r = httpx.post(
        f"{y['base']}/chat/completions",
        headers={"Authorization": f"Bearer {y['anahtar']}",
                 "content-type": "application/json"},
        json={"model": y["model"], "max_tokens": max_tokens,
              "messages": [{"role": "system", "content": sistem},
                           {"role": "user", "content": kullanici}]},
        timeout=ZAMAN_ASIMI)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


def _google(y: dict, sistem: str, kullanici: str, max_tokens: int) -> str:
    """Gemini çağrısı — kimlik biçimi ve düşünme ayarı otomatik denenir.

    İki tuzak var:

    1. Google, AI Studio'da eski `AIza…` anahtarlarının yanında yeni `AQ.…`
       biçimini vermeye başladı. Eskisi `x-goog-api-key`, yenisi bazı
       hesaplarda `Authorization: Bearer` istiyor.
    2. Yeni "flash" modelleri yanıt öncesi düşünür. Küçük bir
       `maxOutputTokens` ile model bütün bütçeyi düşünmeye harcar ve istek
       zaman aşımına uğrar. Bu yüzden düşünmeyi kapatmayı deneriz; model
       bu alanı tanımazsa alansız bir kez daha gönderilir.
    """
    url = f"{y['base']}/models/{y['model']}:generateContent"

    def govde(dusunmeyi_kapat: bool) -> dict:
        ayar = {"maxOutputTokens": max_tokens}
        if dusunmeyi_kapat:
            ayar["thinkingConfig"] = {"thinkingBudget": 0}
        return {"systemInstruction": {"parts": [{"text": sistem}]},
                "contents": [{"role": "user", "parts": [{"text": kullanici}]}],
                "generationConfig": ayar}

    api_basligi = {"content-type": "application/json",
                   "x-goog-api-key": y["anahtar"]}
    bearer_basligi = {"content-type": "application/json",
                      "Authorization": f"Bearer {y['anahtar']}"}
    basliklar = ([bearer_basligi, api_basligi] if y["anahtar"].startswith("AQ.")
                 else [api_basligi, bearer_basligi])

    denemeler = [(b, d) for d in (True, False) for b in basliklar]
    son_hata = None
    for i, (baslik, kapat) in enumerate(denemeler):
        try:
            r = httpx.post(url, headers=baslik, json=govde(kapat),
                           timeout=ZAMAN_ASIMI)
            r.raise_for_status()
            adaylar = r.json().get("candidates", [])
            if not adaylar:
                return ""
            return "".join(p.get("text", "") for p in
                           adaylar[0].get("content", {}).get("parts", []))
        except httpx.HTTPStatusError as exc:
            son_hata = exc
            kod = exc.response.status_code
            # 401/403 → kimlik biçimi; 400 → düşünme ayarı desteklenmiyor
            if kod not in (400, 401, 403) or i == len(denemeler) - 1:
                raise
    if son_hata:
        raise son_hata
    return ""


def _tek_cagri(y: dict, sistem: str, kullanici: str, max_tokens: int) -> str:
    if y["saglayici"] == "anthropic":
        return _anthropic(y, sistem, kullanici, max_tokens)
    if y["saglayici"] == "google":
        return _google(y, sistem, kullanici, max_tokens)
    return _openai_uyumlu(y, sistem, kullanici, max_tokens)


def _cagir(y: dict, sistem: str, kullanici: str, max_tokens: int) -> str:
    """Geçici sunucu hatalarında artan aralıkla yeniden dener."""
    son_hata = None
    for deneme in range(YENIDEN_DENEME):
        try:
            return _tek_cagri(y, sistem, kullanici, max_tokens)
        except httpx.HTTPStatusError as exc:
            son_hata = exc
            if exc.response.status_code not in GECICI_KODLAR:
                raise
        except (httpx.ConnectError, httpx.ReadTimeout) as exc:
            son_hata = exc
        if deneme < YENIDEN_DENEME - 1:
            # 1,5 sn → 3 sn, üstüne küçük bir rastgelelik
            time.sleep(1.5 * (deneme + 1) + random.uniform(0, 0.5))
    raise son_hata


def sor(sistem: str, kullanici: str, max_tokens: int = 2000,
        db=None) -> Optional[str]:
    """Metin döndürür; sağlayıcı yoksa ya da hata olursa None.

    Hata uygulamayı durdurmaz: çağıran taraf kural tabanlı yola düşer.
    """
    y = yapilandirma(db)
    if y["saglayici"] == "none" or not y["base"]:
        return None
    try:
        return _cagir(y, sistem, kullanici, max_tokens)
    except Exception:
        return None


def json_sor(sistem: str, kullanici: str, max_tokens: int = 2000,
             db=None) -> Optional[dict]:
    """Yanıtı JSON olarak ayrıştırır; başarısızsa None."""
    ham = sor(sistem, kullanici, max_tokens, db)
    if not ham:
        return None
    metin = ham.strip()
    if "```" in metin:
        parcalar = metin.split("```")
        if len(parcalar) >= 2:
            metin = parcalar[1]
            if metin.lstrip().lower().startswith("json"):
                metin = metin.lstrip()[4:]
    metin = metin.strip()
    # model açıklama cümlesi eklediyse ilk JSON nesnesini kes
    if not metin.startswith("{"):
        bas = metin.find("{")
        son = metin.rfind("}")
        if bas == -1 or son <= bas:
            return None
        metin = metin[bas:son + 1]
    try:
        veri = json.loads(metin)
        return veri if isinstance(veri, dict) else None
    except Exception:
        return None


def baglanti_testi(db=None) -> dict:
    """Ayar sayfasındaki 'Bağlantıyı sına' düğmesi.

    Gerçek bir çağrı yapar; hata varsa nedenini açıkça döndürür.
    """
    y = yapilandirma(db)
    if y["saglayici"] == "none":
        return {"ok": False, "mesaj": y["neden"] or "Sağlayıcı kapalı",
                "saglayici": "none"}
    if not y["base"]:
        return {"ok": False,
                "mesaj": "Taban adres boş. OpenAI uyumlu bir uç nokta "
                         "kullanıyorsanız adresi girin.",
                "saglayici": y["saglayici"]}

    t0 = time.perf_counter()
    try:
        # Düşünen modeller küçük bütçeyi düşünmeye harcayıp boş döner ya da
        # zaman aşımına uğrar; sınama bütçesi bu yüzden geniş tutulur.
        cevap = _cagir(y, "Yalnızca istenen kelimeyi yaz, başka hiçbir şey yazma.",
                       "TAMAM yaz.", 512)
        ms = int((time.perf_counter() - t0) * 1000)
        if not (cevap or "").strip():
            return {"ok": False, "saglayici": y["saglayici"], "model": y["model"],
                    "mesaj": "Model boş yanıt verdi. Model adını kontrol edin."}
        return {"ok": True, "saglayici": y["saglayici"], "model": y["model"],
                "ms": ms, "mesaj": f"Bağlantı başarılı ({ms} ms): "
                                   f"{cevap.strip()[:40]}"}
    except httpx.HTTPStatusError as exc:
        kod = exc.response.status_code
        aciklama = {
            401: "Anahtar geçersiz ya da süresi dolmuş.",
            403: "Anahtar bu modele erişemiyor.",
            404: ("Model bulunamadı ya da artık yayında değil. Sağlayıcının "
                  "yanıtında önerilen model adını Ayarlar > Model alanına yazın."),
            400: "İstek reddedildi. Anahtar ya da model adı uyumsuz olabilir.",
            429: "Kota doldu ya da istek sınırı aşıldı.",
            503: ("Model şu anda aşırı yüklü. Birkaç deneme yapıldı, hepsi "
                  "reddedildi. Biraz sonra yeniden deneyin ya da Ayarlar > "
                  "Model alanına daha hafif bir model yazın."),
        }.get(kod, f"Sunucu {kod} döndürdü.")
        govde = ""
        try:
            govde = exc.response.text[:200]
        except Exception:
            pass
        ek = ""
        if (y["saglayici"] == "google" and y["anahtar"].startswith("AQ.")
                and kod in (401, 403)):
            ek = (" Not: Google'ın yeni 'AQ.' anahtarları bazı hesaplarda "
                  "Gemini REST ucunda çalışmıyor. AI Studio'dan 'AIza' ile "
                  "başlayan bir anahtar alın ya da başka bir sağlayıcı "
                  "kullanın.")
        return {"ok": False, "saglayici": y["saglayici"], "model": y["model"],
                "mesaj": f"{aciklama} {govde}{ek}".strip()}
    except Exception as exc:
        ipucu = ""
        if "timed out" in str(exc).lower():
            ipucu = (" Model çok yavaş yanıt veriyor olabilir; Ayarlar > Model "
                     "alanına daha küçük bir model yazıp yeniden deneyin.")
        return {"ok": False, "saglayici": y["saglayici"], "model": y["model"],
                "mesaj": f"Bağlanılamadı: {exc}{ipucu}"}
