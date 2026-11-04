"""Küçük ortak yardımcılar: sayı, metin ve zaman güvenliği."""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Optional

# openpyxl'in reddettiği ve CSV'yi bozan denetim karakterleri
KONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Excel'de formül olarak yorumlanan baş karakterler
FORMUL_BASI = ("=", "+", "-", "@", "\t", "\r")


def temiz_metin(deger, uzunluk: int = 0) -> str:
    """Denetim karakterlerini atar, istenirse kırpar."""
    s = KONTROL.sub(" ", str(deger if deger is not None else ""))
    s = s.replace(" ", " ").replace(" ", " ").strip()
    if uzunluk and len(s) > uzunluk:
        s = s[:uzunluk]
    return s


def csv_guvenli(deger) -> str:
    """CSV/Excel formül enjeksiyonunu engeller.

    '=SUM(...)' gibi bir hücre, elektronik tabloda açıldığında formül olarak
    çalışır. Başına tek tırnak koyarak metne çeviririz.
    """
    s = temiz_metin(deger)
    if s.startswith(FORMUL_BASI):
        return "'" + s
    return s


def sonlu(deger, ad: str = "değer") -> float:
    """NaN ve sonsuzu reddeder; JSON ve PostgreSQL bunları kabul etmez."""
    try:
        d = float(deger)
    except (TypeError, ValueError):
        raise ValueError(f"{ad} sayı değil")
    if not math.isfinite(d):
        raise ValueError(f"{ad} geçerli bir sayı değil (NaN/sonsuz)")
    return d


def sonlu_veya(deger, varsayilan: float = 0.0) -> float:
    """Hata fırlatmadan güvenli sayıya çevirir."""
    try:
        return sonlu(deger)
    except ValueError:
        return varsayilan


def utc(zaman: Optional[dt.datetime]) -> Optional[dt.datetime]:
    """Naive (SQLite) ya da aware (PostgreSQL) zamanı UTC'ye getirir."""
    if zaman is None:
        return None
    if zaman.tzinfo is None:
        return zaman.replace(tzinfo=dt.timezone.utc)
    return zaman.astimezone(dt.timezone.utc)


def simdi() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
