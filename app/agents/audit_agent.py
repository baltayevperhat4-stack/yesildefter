"""Denetim ajanı — tutarsızlık ve anomali yakalar.

Doğrulayıcının soracağı soruları, doğrulayıcıdan önce sorar: eksik dönem,
aykırı tüketim, birim uyuşmazlığı, varsayım tabanlı faktör, üretim verisi
olmadan ürün bazlı hesap.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings_store as A
from ..core.util import temiz_metin
from ..messages import mesaj
from ..models import Activity, Document, Emission, Facility, Finding
from .base import Agent, AgentResult, iz_birak

AYKIRI_KAT = 2.5     # medyanın kaç katı aykırı sayılır
MIN_SERI = 4         # aykırı testi için en az kaç dönem gerekir


class AuditAgent(Agent):
    name = "denetim"
    title_tr = "Denetim ajanı"

    def run(self, db: Session, facility_id: int, **kw) -> AgentResult:
        tesis = db.get(Facility, facility_id)
        if tesis is None:
            return AgentResult(self.name, False, mesaj("tr", "ajan.tesis_yok"),
                               code="ajan.tesis_yok")

        # önceki çözülmemiş bulgular temizlenir, yeniden üretilir
        for f in db.scalars(select(Finding).where(
                Finding.facility_id == facility_id, Finding.resolved == 0)):
            db.delete(f)
        db.flush()

        satirlar: List[Activity] = list(db.scalars(
            select(Activity).join(Document).where(Document.facility_id == facility_id)))

        bulgular: List[Finding] = []

        def ekle(severity: str, code: str, activity_id=None, **params):
            """Bulguyu KOD + PARAMETRE olarak saklar.

            Türkçe metin dışa aktarım ve denetim izi için üretilir; ekranda
            kullanıcının dilinde yeniden kurulur."""
            temiz = {k: temiz_metin(v, 300) if isinstance(v, str) else v
                     for k, v in params.items()}
            bulgular.append(Finding(
                facility_id=facility_id, activity_id=activity_id,
                severity=severity, code=code, params=temiz,
                message=temiz_metin(mesaj("tr", f"bulgu.{code}", **temiz), 900)))

        # 1) onay bekleyen satırlar
        bekleyen = [a for a in satirlar if a.status == "onay_bekliyor"]
        for a in bekleyen:
            ekle("uyari", "onay_bekliyor", a.id,
                 guven=round(a.confidence * 100), esik=round(A.esik(db) * 100),
                 satir=a.source_line[:90])

        # 2) birim uyuşmazlığı notu
        for a in satirlar:
            if a.note_code == "bulgu.birim_uyusmazligi" and a.note_params:
                ekle("uyari", "birim_uyusmazligi", a.id, **a.note_params)

        # 3) dönem boşluğu — aynı faktörde eksik ay
        seriler = defaultdict(list)
        for a in satirlar:
            if a.period:
                seriler[a.factor_key].append(a.period)
        for fkey, donemler in seriler.items():
            aylar = sorted({d for d in donemler if len(d) == 7})
            # Yalnızca aylık seri gibi görünen kalemlerde boşluk aranır;
            # çeyreklik ya da tek seferlik alımlar yanlış uyarı üretmesin.
            if len(aylar) >= 6:
                yil_ay = [(int(d[:4]), int(d[5:7])) for d in aylar]
                beklenen = []
                y, m = yil_ay[0]
                while (y, m) <= yil_ay[-1]:
                    beklenen.append((y, m))
                    m += 1
                    if m == 13:
                        y, m = y + 1, 1
                eksik = [f"{y}-{m:02d}" for (y, m) in beklenen if (y, m) not in yil_ay]
                if eksik:
                    ekle("uyari", "donem_boslugu", faktor=fkey,
                         donemler=", ".join(eksik[:6])
                         + (" …" if len(eksik) > 6 else ""))

        # 4) aykırı değer
        gruplar = defaultdict(list)
        for a in satirlar:
            gruplar[a.factor_key].append(a)
        for fkey, grup in gruplar.items():
            if len(grup) < MIN_SERI:
                continue
            degerler = [a.value for a in grup]
            med = statistics.median(degerler)
            if med <= 0:
                continue
            for a in grup:
                if a.value > med * AYKIRI_KAT:
                    ekle("yuksek", "aykiri_deger", a.id, faktor=fkey,
                         donem=a.period or "—",
                         deger=f"{a.value:,.0f}".replace(",", " "),
                         birim=a.unit, kat=f"{a.value / med:.1f}")
                elif a.value * AYKIRI_KAT < med:
                    ekle("uyari", "dusuk_deger", a.id, faktor=fkey,
                         donem=a.period or "—",
                         deger=f"{a.value:,.0f}".replace(",", " "),
                         birim=a.unit)

        # 5) varsayım tabanlı faktörler
        varsayimlar = set()
        tedarikci_ile = set()
        for a in satirlar:
            if not a.emission:
                continue
            if a.emission.factor_tier == "varsayim":
                varsayimlar.add(a.factor_key)
            elif a.emission.factor_tier == "tedarikci":
                tedarikci_ile.add(a.factor_key)
        for fkey in sorted(tedarikci_ile):
            ekle("bilgi", "tedarikci_faktor", faktor=fkey)
        for fkey in sorted(varsayimlar):
            ekle("bilgi", "varsayim_faktor", faktor=fkey)

        # 6) aynı dönem iki kez — çoğu zaman aynı belgenin tekrar yüklenmesi
        gorulen = defaultdict(list)
        for a in satirlar:
            if a.status == "onayli" and a.period:
                gorulen[(a.factor_key, a.period)].append(a)
        for (fkey, donem), grup in sorted(gorulen.items()):
            if len(grup) > 1:
                ekle("yuksek", "mukerrer_kayit", faktor=fkey, donem=donem,
                     adet=len(grup),
                     satirlar=", ".join("#" + str(a.id) for a in grup[:6]))

        # 7) üretim verisi yoksa ürün bazlı hesap yapılamaz
        if tesis.production_ton <= 0:
            ekle("yuksek", "uretim_yok")

        # 8) hiç Kapsam 2 verisi yoksa
        kapsamlar = {a.emission.scope for a in satirlar if a.emission}
        if 2 not in kapsamlar:
            ekle("uyari", "kapsam2_yok")
        if 1 not in kapsamlar:
            ekle("uyari", "kapsam1_yok")

        for b in bulgular:
            db.add(b)
        db.flush()

        yuksek = sum(1 for b in bulgular if b.severity == "yuksek")
        iz_birak(db, "facility", facility_id, "denetim.tarama",
                 {"bulgu": len(bulgular), "yuksek": yuksek})

        if bulgular:
            kod, par = "ajan.denetim.ok", {"bulgu": len(bulgular), "yuksek": yuksek}
        else:
            kod, par = "ajan.denetim.temiz", {}
        return AgentResult(self.name, True, mesaj("tr", kod, **par),
                           code=kod, params=par,
                           data={"bulgu": len(bulgular), "yuksek": yuksek,
                                 "onay_bekleyen": len(bekleyen)})
