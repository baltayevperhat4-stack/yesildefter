"""Tedarik zinciri ajanı — Kapsam 3 verisi için tedarikçiyi izler.

Dürüstlük notu: SMTP ayarları tanımlıysa istek gerçekten e-postayla gider ve
durum "gonderildi" olur. Tanımlı değilse istek yalnızca *hazırlanır*
("hazirlandi") ve ajan bunu uyarı olarak bildirir — gönderilmemiş bir isteği
gönderilmiş gibi göstermeyiz.

Tedarikçi gerçek değerini bildirdiğinde (`yanit_kaydet`), faktör ajanı bir
sonraki çalışmasında varsayım faktörü yerine o değeri kullanır.
"""

from __future__ import annotations

import datetime as dt
from email.message import EmailMessage
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings_store as A
from ..core.util import simdi, sonlu, utc
from ..messages import mesaj
from ..models import Facility, Supplier
from .base import Agent, AgentResult, iz_birak

HATIRLATMA_GUN = 7
MAX_HATIRLATMA = 3


def eposta_yapilandirildi(db=None) -> bool:
    s = A.smtp_ayarlari(db)
    return bool(s["host"] and s["from"])


def _istek_metni(tesis: Facility, t: Supplier, db=None) -> str:
    """Metin. Dil modeli varsa taslağı o yazar, yoksa sabit şablon."""
    if db is not None:
        try:
            from ..llm.explain import tedarikci_eposta_taslagi
            taslak = tedarikci_eposta_taslagi(db, tesis.name, t.name,
                                              t.material or "malzeme")
            if taslak and len(taslak.strip()) > 80:
                return taslak.strip()
        except Exception:
            pass
    return (
        f"Sayın {t.name} yetkilisi,\n\n"
        f"{tesis.name}, AB Sınırda Karbon Düzenleme Mekanizması (CBAM) ve "
        f"Türkiye Emisyon Ticaret Sistemi kapsamındaki raporlaması için "
        f"tedarik ettiğiniz '{t.material}' kaleminin birim gömülü karbon "
        f"değerine ihtiyaç duymaktadır.\n\n"
        f"Lütfen değeri kgCO2e/birim olarak ve hesaplama yönteminizi "
        f"(GHG Protocol / ISO 14064 vb.) belirterek paylaşınız.\n\n"
        f"Bu bilgi olmadan, hesaplamada sektör varsayımı kullanılmak zorunda "
        f"kalınmakta ve bu da genellikle gerçek değerden yüksek çıkmaktadır.\n\n"
        f"Teşekkürler,\n{tesis.name}\nYeşilDefter üzerinden gönderilmiştir."
    )


def _eposta_gonder(tesis: Facility, t: Supplier, db=None) -> tuple[bool, str]:
    """E-postayı gönderir. (basarili, mesaj) döndürür."""
    ayar = A.smtp_ayarlari(db)
    if not eposta_yapilandirildi(db):
        return False, "SMTP yapılandırılmamış"
    if not t.email:
        return False, "Tedarikçinin e-posta adresi yok"
    try:
        import smtplib

        msg = EmailMessage()
        msg["Subject"] = f"Gömülü karbon verisi talebi — {t.material}"
        msg["From"] = ayar["from"]
        msg["To"] = t.email
        msg.set_content(_istek_metni(tesis, t, db))

        with smtplib.SMTP(ayar["host"], ayar["port"], timeout=20) as sm:
            if ayar["tls"]:
                sm.starttls()
            if ayar["user"]:
                sm.login(ayar["user"], ayar["password"])
            sm.send_message(msg)
        return True, "gönderildi"
    except Exception as exc:
        return False, f"gönderilemedi: {exc}"


class SupplierAgent(Agent):
    name = "tedarik"
    title_tr = "Tedarik zinciri ajanı"

    def run(self, db: Session, facility_id: int, **kw) -> AgentResult:
        tesis = db.get(Facility, facility_id)
        if tesis is None:
            return AgentResult(self.name, False, mesaj("tr", "ajan.tesis_yok"),
                               code="ajan.tesis_yok")

        tedarikciler: List[Supplier] = list(db.scalars(
            select(Supplier).where(Supplier.facility_id == facility_id)))
        if not tedarikciler:
            return AgentResult(self.name, True,
                               mesaj("tr", "ajan.tedarik.yok"),
                               code="ajan.tedarik.yok",
                               data={"toplam": 0, "istek": 0, "hatirlatma": 0,
                                     "yanit": 0, "bekleyen": 0,
                                     "kapsama_yuzde": 0.0})

        simdi_ = simdi()
        istek, hatirlatma, yanit = 0, 0, 0
        uyari_kodlari: List[str] = []
        if not eposta_yapilandirildi(db):
            uyari_kodlari.append("ajan.tedarik.smtp_yok")

        for t in tedarikciler:
            if t.status == "yanitladi":
                yanit += 1
                continue

            # 1) hiç istek hazırlanmamış
            if t.requested_at is None:
                t.requested_at = simdi_
                ok, sonuc_mesaji = _eposta_gonder(tesis, t, db)
                t.status = "gonderildi" if ok else "hazirlandi"
                istek += 1
                iz_birak(db, "supplier", t.id, "tedarik.istek",
                         {"tedarikci": t.name, "malzeme": t.material,
                          "sonuc": sonuc_mesaji if ok else
                          (sonuc_mesaji or "hazırlandı, gönderilmedi")})
                continue

            # 2) hatırlatma zamanı geldi mi — ve daha önce bugün yapılmadı mı
            son = utc(t.last_reminder_at) or utc(t.requested_at)
            gecen = (simdi_ - son).days if son else 0
            if gecen >= HATIRLATMA_GUN and t.reminder_count < MAX_HATIRLATMA:
                t.last_reminder_at = simdi_
                t.reminder_count += 1
                ok, sonuc_mesaji = _eposta_gonder(tesis, t, db)
                t.status = "hatirlatildi"
                hatirlatma += 1
                iz_birak(db, "supplier", t.id, "tedarik.hatirlatma",
                         {"tedarikci": t.name, "gecen_gun": gecen,
                          "sira": t.reminder_count,
                          "sonuc": sonuc_mesaji if ok else "hazırlandı"})
            elif t.reminder_count >= MAX_HATIRLATMA and t.status != "yanitsiz":
                t.status = "yanitsiz"
                iz_birak(db, "supplier", t.id, "tedarik.yanitsiz",
                         {"tedarikci": t.name,
                          "hatirlatma": t.reminder_count})

        db.flush()

        bekleyen = sum(1 for t in tedarikciler if t.status != "yanitladi")
        kapsam = yanit / len(tedarikciler) * 100
        par = {"toplam": len(tedarikciler), "yanit": yanit,
               "bekleyen": bekleyen, "kapsama": f"{kapsam:.0f}"}
        return AgentResult(
            self.name, True, mesaj("tr", "ajan.tedarik.ok", **par),
            code="ajan.tedarik.ok", params=par,
            data={"toplam": len(tedarikciler), "istek": istek,
                  "hatirlatma": hatirlatma, "yanit": yanit,
                  "bekleyen": bekleyen, "kapsama_yuzde": round(kapsam, 1),
                  "eposta": eposta_yapilandirildi(db)},
            warnings=[mesaj("tr", u) for u in uyari_kodlari],
            warning_codes=uyari_kodlari,
        )


def yanit_kaydet(db: Session, supplier_id: int, kgco2e_per_unit: float,
                 factor_key: Optional[str] = None) -> bool:
    """Tedarikçi yanıtını kaydeder ve denetim izine yazar."""
    t = db.get(Supplier, supplier_id)
    if t is None:
        return False
    deger = sonlu(kgco2e_per_unit, "Tedarikçi değeri")
    if deger < 0:
        raise ValueError("Tedarikçi değeri negatif olamaz")
    t.reported_kgco2e_per_unit = deger
    if factor_key:
        t.factor_key = factor_key
    t.responded_at = simdi()
    t.status = "yanitladi"
    db.flush()
    iz_birak(db, "supplier", t.id, "tedarik.yanit",
             {"tedarikci": t.name, "deger": deger, "faktor": t.factor_key},
             actor=t.name)
    return True
