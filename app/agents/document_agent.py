"""Belge ajanı — fatura, irsaliye ve sayaç çıktısından faaliyet verisi çıkarır.

Yenilik optik okuma değildir. Yenilik, okunan değerin hangi kapsama ait
olduğunun belirlenmesi ve emin olunmadığında sorulmasıdır: güven skoru eşiğin
altındaysa satır onay kuyruğuna düşer, sistem tahmin yürütmez.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from .. import settings_store as A
from ..config import MAX_DONEM
from ..core.util import temiz_metin
from ..core import factors as F
from ..llm import prompts as P
from ..llm import provider as llm
from ..messages import mesaj
from ..models import Activity, Document
from .base import Agent, AgentResult, iz_birak

# 1.234,56 / 1,234.56 / 58400 biçimlerini yakalar
SAYI = r"(\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?|\d+(?:[.,]\d+)?)"
SAYI_RE = re.compile(SAYI)

# Birim sözlüğü. Uzun biçimler önce gelir ki "ton-km", "ton"dan önce eşleşsin.
BIRIM_SIRA = [
    ("ton-km", r"ton\s*-\s*km|tonkm|ton\s+km"),
    ("m3", r"m3|m³|metrek[üu]p|sm3|nm3"),
    ("kWh", r"kwh|kw/h|kilovatsaat"),
    ("GJ", r"gj|gigajoule"),
    ("lt", r"lt|litre|liter"),
    ("kg", r"kg|kilogram"),
    ("ton", r"ton|tn"),
]
BIRIM_RE = re.compile(
    "|".join(f"(?P<b{i}>{kal})" for i, (_, kal) in enumerate(BIRIM_SIRA)),
    re.IGNORECASE,
)
DONEM = re.compile(r"(0[1-9]|1[0-2])[./-](20\d{2})")
DONEM2 = re.compile(r"(20\d{2})[./-](0[1-9]|1[0-2])")

# Tarife / fiyat satırları faaliyet verisi değildir. Türk faturalarında
# "Birim Fiyat: 7,40 TL/m3" gibi satırlar sıkça geçer; birimden önceki sayı
# miktar değil fiyattır. Bunları hiç almamak, yanlış almaktan iyidir.
FIYAT_IPUCU = re.compile(
    r"birim\s*fiyat|fiyat[ıi]?\s*:|tarife|bedel|kdv|vergi|otv|ötv|"
    r"matrah|iskonto|indirim|yuvarlama|unit\s*price",
    re.IGNORECASE)
# "TL/m3", "₺/kWh", "EUR/ton" gibi oran gösterimleri
ORAN = re.compile(r"(?:tl|try|₺|usd|\$|eur|€)\s*/\s*[a-zçğıöşü³]", re.IGNORECASE)


def sayiya_cevir(ham: str) -> Optional[float]:
    """Türkçe ve İngilizce sayı biçimlerini float'a çevirir."""
    s = (ham or "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        # son ayraç ondalıktır
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        tam, _, kesir = s.rpartition(",")
        s = f"{tam.replace('.', '')}.{kesir}" if len(kesir) <= 2 else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif "." in s:
        tam, _, kesir = s.rpartition(".")
        if len(kesir) == 3 and tam.isdigit():   # 58.400 = binlik
            s = tam + kesir
    try:
        return float(s)
    except ValueError:
        return None


def birim_bul(satir: str) -> Optional[str]:
    """Satırdaki ilk birimi döndürür."""
    bulgu = _birim_eslesmesi(satir)
    return bulgu[0] if bulgu else None


def _birim_eslesmesi(satir: str):
    """(birim, baslangic, bitis) döndürür; yoksa None."""
    for m in BIRIM_RE.finditer(satir):
        for i, (ad, _) in enumerate(BIRIM_SIRA):
            if m.group(f"b{i}"):
                onceki = satir[m.start() - 1] if m.start() else " "
                sonraki = satir[m.end()] if m.end() < len(satir) else " "
                # sözcük içinde kalan eşleşmeyi atla (örn. "kalite" içindeki "lt")
                if onceki.isalpha() or sonraki.isalpha():
                    break
                return ad, m.start(), m.end()
    return None


def _miktar_sec(satir: str, anahtar_sonu: int = 0):
    """Birime en yakın sayıyı seçer; birim yoksa anahtar kelimeden sonrakini.

    Fatura satırlarında miktar birimin solunda, tutar ise sağındadır. Bu yüzden
    birimin soluna en yakın sayı miktardır. Bu kural, tutarı miktar sanma
    hatasını önler.
    """
    sayilar = [(sayiya_cevir(m.group(0)), m.start(), m.end())
               for m in SAYI_RE.finditer(satir)]
    sayilar = [s for s in sayilar if s[0] is not None and s[0] > 0]
    if not sayilar:
        return None, None, len(sayilar)

    birim = _birim_eslesmesi(satir)
    if birim is None:
        # Birim yoksa anahtar kelimeden sonraki ilk sayı miktardır; yoksa
        # satırdaki ilk sayı alınır. Tutarı miktar sanmamak için en büyük
        # sayıya bakılmaz.
        sonrakiler = [s for s in sayilar if s[1] >= anahtar_sonu]
        secilen = (min(sonrakiler, key=lambda s: s[1]) if sonrakiler
                   else min(sayilar, key=lambda s: s[1]))
        return secilen[0], None, len(sayilar)

    _, b_bas, b_bit = birim
    soldakiler = [s for s in sayilar if s[2] <= b_bas]
    if soldakiler:
        secilen = max(soldakiler, key=lambda s: s[2])
        return secilen[0], birim[0], len(sayilar)
    sagdakiler = [s for s in sayilar if s[1] >= b_bit]
    if sagdakiler:
        secilen = min(sagdakiler, key=lambda s: s[1])
        return secilen[0], birim[0], len(sayilar)
    return sayilar[0][0], birim[0], len(sayilar)


def donem_bul(metin: str) -> str:
    m = DONEM.search(metin)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    m = DONEM2.search(metin)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return ""


def metin_oku(yol: str | Path) -> str:
    """Dosyadan ham metin çıkarır (pdf, csv, txt)."""
    p = Path(yol)
    son = p.suffix.lower()
    if son == ".pdf":
        try:
            import pdfplumber
            parcalar = []
            with pdfplumber.open(str(p)) as pdf:
                for sayfa in pdf.pages:
                    parcalar.append(sayfa.extract_text() or "")
            return "\n".join(parcalar)
        except Exception:
            return ""
    if son in (".csv", ".tsv"):
        ayrac = "\t" if son == ".tsv" else ","
        satirlar = []
        with open(p, newline="", encoding="utf-8", errors="replace") as fh:
            for row in csv.reader(fh, delimiter=ayrac):
                satirlar.append(" ".join(row))
        return "\n".join(satirlar)
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def fiyat_satiri_mi(satir: str) -> bool:
    """Satır, miktar değil birim fiyat/tarife taşıyorsa True."""
    return bool(FIYAT_IPUCU.search(satir) or ORAN.search(satir))


def _aday_satirlar(metin: str, ulke: str | None = None) -> List[dict]:
    """Kural tabanlı çıkarım: her satırda faktör + miktar + birim arar."""
    adaylar: List[dict] = []
    genel_donem = donem_bul(metin)
    for ham in metin.splitlines():
        satir = temiz_metin(ham)
        if len(satir) < 4:
            continue
        if fiyat_satiri_mi(satir):
            continue
        eslesme = F.find_factor_match(satir, ulke)
        if not eslesme:
            continue
        fkey, _, anahtar_sonu = eslesme
        miktar, birim, sayi_adedi = _miktar_sec(satir, anahtar_sonu)
        if miktar is None:
            continue
        faktor = F.get_factor(fkey)

        if birim and birim.lower() == faktor.unit.lower():
            guven = 0.95
        elif birim is None:
            guven = 0.72
        else:
            guven = 0.55
        if sayi_adedi > 4:
            guven -= 0.08
        if faktor.tier == "varsayim":
            guven -= 0.05
        guven = round(max(0.3, min(0.99, guven)), 2)

        adaylar.append({
            "factor_key": fkey,
            "value": miktar,
            "unit": faktor.unit,
            "read_unit": birim or "",
            "confidence": guven,
            "period": temiz_metin(donem_bul(satir) or genel_donem, MAX_DONEM),
            "source_line": temiz_metin(satir, 400),
        })
    return adaylar


def _satir_temizle(r: dict) -> Optional[dict]:
    """Modelden gelen bir satırı doğrular; geçersizse None."""
    fkey = str(r.get("factor_key") or "")
    if fkey not in F.FUELS and fkey not in F.INTENSITIES:
        return None
    try:
        deger = float(r.get("value"))
    except (TypeError, ValueError):
        return None
    if deger <= 0 or not (deger == deger) or deger in (float("inf"),):
        return None
    faktor = F.get_factor(fkey)
    try:
        guven = float(r.get("confidence", 0.8))
    except (TypeError, ValueError):
        guven = 0.8
    return {
        "factor_key": fkey,
        "value": deger,
        "unit": faktor.unit,
        "read_unit": temiz_metin(r.get("unit", ""), 20),
        "confidence": round(min(0.99, max(0.1, guven)), 2),
        "period": temiz_metin(r.get("period", ""), MAX_DONEM),
        "source_line": temiz_metin(r.get("source_line", ""), 400),
        "llm_note": temiz_metin(r.get("note", ""), 200),
    }


def _llm_cikarim(metin: str, ulke: str, db=None) -> Optional[List[dict]]:
    """Dil modeliyle çıkarım. Başarısızsa None döner, çağıran kurala düşer."""
    cevap = llm.json_sor(P.CIKARIM_SISTEM, P.cikarim_kullanici(metin, ulke),
                         max_tokens=3000, db=db)
    if not cevap or not isinstance(cevap.get("rows"), list):
        return None
    cikti = [t for t in (_satir_temizle(r) for r in cevap["rows"]) if t]
    return cikti


def _llm_faktor_onerisi(satirlar: List[str], db=None) -> List[dict]:
    """Kuralın tanımadığı satırlar için öneri.

    Dönen satır HER ZAMAN onay kuyruğuna düşecek güvenle işaretlenir:
    model önerisi hiçbir koşulda doğrudan hesaba girmez.
    """
    if not satirlar or not A.get_bool("llm_faktor_onerisi", db):
        return []
    cevap = llm.json_sor(P.FAKTOR_SISTEM, P.faktor_kullanici(satirlar),
                         max_tokens=1500, db=db)
    if not cevap or not isinstance(cevap.get("rows"), list):
        return []
    esik = A.esik(db)
    cikti = []
    for r in cevap["rows"]:
        t = _satir_temizle(r)
        if t is None:
            continue
        t["confidence"] = round(min(t["confidence"], esik - 0.05), 2)
        t["llm_note"] = (t.get("llm_note") or
                         temiz_metin(r.get("reason", ""), 200) or
                         "Yapay zekâ önerisi — onayınız gerekiyor.")
        cikti.append(t)
    return cikti


class DocumentAgent(Agent):
    name = "belge"
    title_tr = "Belge ajanı"

    def run(self, db: Session, document_id: int, **kw) -> AgentResult:
        belge = db.get(Document, document_id)
        if belge is None:
            return AgentResult(self.name, False, "Belge bulunamadı",
                               code="ajan.belge.veri_yok")

        metin = belge.raw_text or ""
        if not metin.strip():
            return AgentResult(self.name, False,
                               mesaj("tr", "ajan.belge.metin_yok"),
                               code="ajan.belge.metin_yok")

        ulke = belge.facility.country if belge.facility else None
        adaylar = _aday_satirlar(metin, ulke)
        cikarim = "kural"
        onerilen = 0

        if llm.kullanilabilir(db):
            # 1) Dil modeliyle tam çıkarım. Başarısızsa kural sonucu kalır.
            llm_sonuc = _llm_cikarim(metin, ulke or "TR", db)
            if llm_sonuc:
                cikarim = "llm"
                adaylar = llm_sonuc

            # 2) Hiçbir yolun tanımadığı satırlar için faktör önerisi.
            taninan = {a["source_line"][:60] for a in adaylar}
            bilinmeyen = [
                sat for sat in (temiz_metin(x, 200) for x in metin.splitlines())
                if len(sat) > 12 and sat[:60] not in taninan
                and not fiyat_satiri_mi(sat)
                and F.find_factor_match(sat, ulke) is None
                and any(ch.isdigit() for ch in sat)
            ]
            oneriler = _llm_faktor_onerisi(bilinmeyen[:25], db)
            if oneriler:
                adaylar = adaylar + oneriler
                onerilen = len(oneriler)
                cikarim = "llm+oneri" if cikarim == "llm" else "kural+oneri"

        belge.extractor = cikarim
        esik = A.esik(db)

        eklenen, onay_bekleyen = 0, 0
        for a in adaylar:
            durum = "onayli" if a["confidence"] >= esik else "onay_bekliyor"
            if durum == "onay_bekliyor":
                onay_bekleyen += 1
            not_metni = a.get("llm_note", "") or ""
            not_kodu, not_par = "", {}
            if a["read_unit"] and a["read_unit"].lower() != a["unit"].lower():
                not_kodu = "bulgu.birim_uyusmazligi"
                not_par = {"okunan": a["read_unit"], "beklenen": a["unit"]}
                not_metni = f"{not_metni} {mesaj('tr', not_kodu, **not_par)}".strip()
            db.add(Activity(
                document_id=belge.id, factor_key=a["factor_key"],
                value=a["value"], unit=a["unit"], period=a["period"],
                confidence=a["confidence"], status=durum,
                source_line=a["source_line"], note=not_metni,
                note_code=not_kodu, note_params=not_par,
            ))
            eklenen += 1

        belge.status = "islendi" if eklenen else "veri_yok"
        db.flush()
        iz_birak(db, "document", belge.id, "belge.cikarim",
                 {"satir": eklenen, "onay_bekleyen": onay_bekleyen,
                  "yapay_zeka_onerisi": onerilen, "yontem": cikarim})

        if eklenen == 0:
            return AgentResult(self.name, False,
                               mesaj("tr", "ajan.belge.veri_yok"),
                               code="ajan.belge.veri_yok")
        par = {"eklenen": eklenen, "oneri": onerilen,
               "bekleyen": onay_bekleyen}
        ozet = mesaj("tr", "ajan.belge.ok", **par)
        if onerilen:
            ozet += mesaj("tr", "ajan.belge.oneri_eki", **par)
        if onay_bekleyen:
            ozet += mesaj("tr", "ajan.belge.bekleyen_eki", **par)
        return AgentResult(self.name, True, ozet,
                           code="ajan.belge.ok", params=par,
                           data={"eklenen": eklenen,
                                 "onay_bekleyen": onay_bekleyen,
                                 "oneri": onerilen,
                                 "yontem": cikarim})
