"""Ayar katmanı — veri tabanı > ortam değişkeni > koddaki varsayılan.

Neden üç katman: sunucuya erişimi olmayan kullanıcı API anahtarını arayüzden
girebilmeli; ortam değişkeniyle kurulmuş bir dağıtım ise bozulmamalı. Veri
tabanında bir değer varsa o kazanır, yoksa ortam değişkenine, o da yoksa
koddaki varsayılana düşer.

Gizli değerler (API anahtarı, SMTP parolası, bot jetonu) arayüzde hiçbir zaman
tam gösterilmez; yalnızca maskelenmiş hâli döner.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config as C
from .core.util import temiz_metin
from .models import Setting, SessionLocal

# ayar anahtarı -> (ortam değişkeni, koddaki varsayılan, gizli mi)
SEMA: Dict[str, tuple] = {
    # --- yapay zekâ
    "llm_api_key":        ("ANTHROPIC_API_KEY", "", True),
    "llm_provider":       ("YD_LLM_PROVIDER", "auto", False),
    "llm_model":          ("YD_LLM_MODEL", "", False),
    "llm_base_url":       ("YD_LLM_BASE_URL", "", False),
    "llm_faktor_onerisi": ("YD_LLM_FACTOR_SUGGEST", "1", False),
    "llm_aciklama":       ("YD_LLM_EXPLAIN", "1", False),
    "llm_eposta_taslagi": ("YD_LLM_EMAIL_DRAFT", "1", False),
    # --- hesaplama
    "confidence_threshold": ("YD_CONFIDENCE_THRESHOLD", "0.90", False),
    "cbam_cert_eur":        ("YD_CBAM_CERT_EUR", "75", False),
    "cbam_yil":             ("YD_CBAM_YEAR", "", False),
    # --- arayüz
    "default_lang": ("YD_DEFAULT_LANG", "tr", False),
    # --- tedarikçiye e-posta
    "smtp_host":     ("YD_SMTP_HOST", "", False),
    "smtp_port":     ("YD_SMTP_PORT", "587", False),
    "smtp_user":     ("YD_SMTP_USER", "", False),
    "smtp_password": ("YD_SMTP_PASSWORD", "", True),
    "smtp_from":     ("YD_SMTP_FROM", "", False),
    "smtp_tls":      ("YD_SMTP_TLS", "1", False),
    # --- Telegram
    "telegram_token":         ("TELEGRAM_BOT_TOKEN", "", True),
    "telegram_allowed_chats": ("TELEGRAM_ALLOWED_CHATS", "", False),
    # --- güvenlik
    "allow_demo_reset": ("YD_ALLOW_DEMO_RESET", "1", False),
}

GIZLI = {k for k, (_, _, gizli) in SEMA.items() if gizli}


def _oku_db(db: Session, key: str) -> Optional[str]:
    satir = db.get(Setting, key)
    if satir is None:
        return None
    return satir.value


def get(key: str, db: Session | None = None) -> str:
    """Ayarın geçerli değerini döndürür."""
    env_adi, varsayilan, _ = SEMA.get(key, ("", "", False))
    kendi = db is None
    if kendi:
        db = SessionLocal()
    try:
        deger = _oku_db(db, key)
    except Exception:
        deger = None
    finally:
        if kendi:
            db.close()
    if deger not in (None, ""):
        return deger
    if env_adi:
        ortam = os.getenv(env_adi)
        if ortam not in (None, ""):
            return ortam
    return varsayilan


def get_bool(key: str, db: Session | None = None) -> bool:
    return str(get(key, db)).strip().lower() in ("1", "true", "evet", "yes", "on")


def get_float(key: str, varsayilan: float, db: Session | None = None) -> float:
    try:
        return float(str(get(key, db)).replace(",", "."))
    except (TypeError, ValueError):
        return varsayilan


def get_int(key: str, varsayilan: int, db: Session | None = None) -> int:
    try:
        return int(float(str(get(key, db))))
    except (TypeError, ValueError):
        return varsayilan


def set_many(db: Session, degerler: Dict[str, str]) -> int:
    """Birden çok ayarı yazar. Boş gizli değer mevcut değeri SİLMEZ."""
    yazilan = 0
    for key, ham in degerler.items():
        if key not in SEMA:
            continue
        deger = temiz_metin(ham, 4000)
        if key in GIZLI and deger == "":
            continue           # kullanıcı maskeli alanı boş bıraktı
        if key in GIZLI and set(deger) <= {"•", "*", "·"}:
            continue           # maskeyi geri göndermiş
        satir = db.get(Setting, key)
        if satir is None:
            db.add(Setting(key=key, value=deger))
        else:
            satir.value = deger
        yazilan += 1
    db.flush()
    return yazilan


def sil(db: Session, key: str) -> bool:
    satir = db.get(Setting, key)
    if satir is None:
        return False
    db.delete(satir)
    db.flush()
    return True


def maskele(deger: str) -> str:
    """Anahtarın yalnızca ilk ve son birkaç karakterini gösterir."""
    if not deger:
        return ""
    if len(deger) <= 10:
        return "•" * len(deger)
    return f"{deger[:6]}{'•' * 10}{deger[-4:]}"


def arayuz_degerleri(db: Session) -> Dict[str, str]:
    """Ayar sayfasına basılacak değerler; gizli olanlar maskelenmiş."""
    cikti = {}
    for key in SEMA:
        deger = get(key, db)
        cikti[key] = maskele(deger) if key in GIZLI else deger
    return cikti


def kaynak(db: Session, key: str) -> str:
    """Değerin nereden geldiği: veri tabanı, ortam değişkeni ya da varsayılan."""
    if _oku_db(db, key) not in (None, ""):
        return "db"
    env_adi, _, _ = SEMA.get(key, ("", "", False))
    if env_adi and os.getenv(env_adi):
        return "env"
    return "varsayilan"


# --------------------------------------------------------- kısa yollar
def esik(db: Session | None = None) -> float:
    """İnsan onayı eşiği; 0,50 ile 0,99 arasına sıkıştırılır."""
    d = get_float("confidence_threshold", C.CONFIDENCE_THRESHOLD, db)
    return min(0.99, max(0.50, d))


def cbam_eur(db: Session | None = None) -> float:
    d = get_float("cbam_cert_eur", C.CBAM_CERT_EUR, db)
    return max(0.0, d)


def demo_sifirlama_acik(db: Session | None = None) -> bool:
    return get_bool("allow_demo_reset", db)


def smtp_ayarlari(db: Session | None = None) -> dict:
    return {
        "host": get("smtp_host", db),
        "port": get_int("smtp_port", 587, db),
        "user": get("smtp_user", db),
        "password": get("smtp_password", db),
        "from": get("smtp_from", db) or get("smtp_user", db),
        "tls": get_bool("smtp_tls", db),
    }


def telegram_ayarlari(db: Session | None = None) -> dict:
    ham = get("telegram_allowed_chats", db)
    izinli = {int(x) for x in ham.replace(" ", "").split(",")
              if x.lstrip("-").isdigit()}
    return {"token": get("telegram_token", db), "izinli": izinli}
