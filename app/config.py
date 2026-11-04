"""Uygulama ayarları — tamamı ortam değişkeniyle geçersiz kılınabilir."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("YD_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Varsayılan SQLite; Railway/üretimde DATABASE_URL ile PostgreSQL verilir.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'yesildefter.db'}")
if DATABASE_URL.startswith("postgres://"):           # Railway eski biçim
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def _bayrak(ad: str, varsayilan: bool) -> bool:
    ham = os.getenv(ad)
    if ham is None:
        return varsayilan
    return ham.strip().lower() in ("1", "true", "evet", "yes", "on")


# İnsan onayı eşiği: güven skoru bunun altındaysa sistem sormadan ilerlemez.
CONFIDENCE_THRESHOLD = float(os.getenv("YD_CONFIDENCE_THRESHOLD", "0.90"))

# CBAM sertifika fiyatı varsayımı (€/tCO2e)
CBAM_CERT_EUR = float(os.getenv("YD_CBAM_CERT_EUR", "75"))

# Dil
DEFAULT_LANG = os.getenv("YD_DEFAULT_LANG", "tr")
LANGS = ["tr", "uz", "ru", "en", "tk"]

# Belge yükleme sınırları
ALLOWED_UPLOAD_EXT = {".pdf", ".csv", ".tsv", ".txt"}
MAX_UPLOAD_BYTES = int(os.getenv("YD_MAX_UPLOAD_MB", "25")) * 1024 * 1024

# Alan uzunluk sınırları — PostgreSQL'de String(n) taşmasını önler
MAX_AD = 200
MAX_SEKTOR = 120
MAX_DOSYA_ADI = 200
MAX_DONEM = 20

# Demo verisini yükleyen uç nokta tüm veri tabanını siler; üretimde kapatın.
ALLOW_DEMO_RESET = _bayrak("YD_ALLOW_DEMO_RESET", True)

# Saklanacak en fazla rapor sayısı (sınırsız büyümeyi önler)
MAX_REPORTS = int(os.getenv("YD_MAX_REPORTS", "20"))

# İsteğe bağlı LLM. Anahtar yoksa sistem kural tabanlı çıkarımla çalışır.
LLM_PROVIDER = os.getenv("YD_LLM_PROVIDER", "auto")     # auto | anthropic | openai | none
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("YD_LLM_MODEL", "claude-sonnet-4-5")

# Telegram botu. Token yoksa bot başlatılmaz, uygulama normal çalışır.
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Yetkili sohbet kimlikleri (virgülle). Boşsa bot kimseye yanıt vermez.
TELEGRAM_ALLOWED_CHATS = {
    int(x) for x in os.getenv("TELEGRAM_ALLOWED_CHATS", "").replace(" ", "").split(",")
    if x.lstrip("-").isdigit()
}

# Tedarikçiye e-posta gönderimi (SMTP). Tanımsızsa istek yalnızca hazırlanır,
# gönderildi olarak işaretlenmez.
SMTP_HOST = os.getenv("YD_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("YD_SMTP_PORT", "587"))
SMTP_USER = os.getenv("YD_SMTP_USER", "")
SMTP_PASSWORD = os.getenv("YD_SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("YD_SMTP_FROM", SMTP_USER)
SMTP_TLS = _bayrak("YD_SMTP_TLS", True)

# Genel erişim parolası (HTTP Basic). Boşsa kimlik doğrulama kapalıdır; yerel
# geliştirmede böyle çalışır. Üretimde YD_PAROL verilmeden yayına alınmamalıdır.
ACCESS_USER = os.getenv("YD_KULLANICI", "jury").strip() or "jury"
ACCESS_PASSWORD = os.getenv("YD_PAROL", "").strip()

APP_NAME = "YeşilDefter"
APP_VERSION = "0.4.1"
