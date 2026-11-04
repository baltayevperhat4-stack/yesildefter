"""Arayüz ve API için toplama (okuma) işlevleri."""

from __future__ import annotations

import csv
import io
from typing import List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .agents.compliance_agent import envanter, son_tarihler
from . import settings_store as A
from .core import calc
from .core import factors as F
from .core.util import csv_guvenli
from .models import (Activity, AuditEvent, Document, Emission, Facility, Finding,
                     Measure, Report, Supplier)


def aktif_tesis(db: Session) -> Optional[Facility]:
    return db.scalars(select(Facility).order_by(Facility.id)).first()


def bekleyen_adet(db: Session, facility_id: int) -> int:
    """Onay bekleyen satır sayısı — tek COUNT sorgusu."""
    return int(db.scalar(
        select(func.count(Activity.id)).join(Document).where(
            Document.facility_id == facility_id,
            Activity.status == "onay_bekliyor")) or 0)


def kullanilan_surumler(db: Session, facility_id: int) -> List[str]:
    """Envanterdeki hesapların faktör sürümleri.

    Birden fazla sürüm varsa dışa aktarımda tek sürüm damgası yanıltıcı olur;
    bu yüzden ayrıca bildirilir.
    """
    q = select(Emission.factor_version).join(Activity).join(Document).where(
        Document.facility_id == facility_id, Activity.status == "onayli")
    return sorted({v for v in db.scalars(q) if v})


def pano(db: Session, facility_id: int) -> dict:
    tesis = db.get(Facility, facility_id)
    env = envanter(db, facility_id)

    gomulu = None
    kacinilan = None
    if tesis and tesis.production_ton > 0:
        dogrudan = calc.urun_birimine_dagit(env["scope1"], tesis.production_ton)
        dolayli = calc.urun_birimine_dagit(env["scope2"], tesis.production_ton)
        gomulu = {"dogrudan": dogrudan, "dolayli": dolayli,
                  "toplam": round(dogrudan + dolayli, 4)}
        if tesis.export_ton_eu > 0:
            kacinilan = calc.kacinilan_maliyet(
                gomulu["toplam"] * tesis.export_ton_eu, tesis.year, A.cbam_eur(db))

    bekleyen_sayi = bekleyen_adet(db, facility_id)
    bulgular = list(db.scalars(select(Finding).where(
        Finding.facility_id == facility_id, Finding.resolved == 0)))
    onlemler = list(db.scalars(select(Measure).where(
        Measure.facility_id == facility_id)))
    belge_sayi = len(list(db.scalars(select(Document.id).where(
        Document.facility_id == facility_id))))

    toplam_azaltim = round(sum(m.tco2e_year for m in onlemler), 2)
    pay = round(toplam_azaltim / env["toplam"] * 100, 1) if env["toplam"] else 0.0

    ets_kapsam = env["toplam"] >= 50_000

    return {
        "tesis": tesis,
        "envanter": env,
        "gomulu": gomulu,
        "kacinilan": kacinilan,
        "bekleyen": bekleyen_sayi,
        "bekleyen_var": bekleyen_sayi > 0,
        "bulgu_sayi": len(bulgular),
        "bulgu_yuksek": sum(1 for b in bulgular if b.severity == "yuksek"),
        "onlem_sayi": len(onlemler),
        "azaltim_tco2e": toplam_azaltim,
        "azaltim_pay": pay,
        "belge_sayi": belge_sayi,
        "ets_kapsam": ets_kapsam,
        "son_tarihler": son_tarihler(),
        "factor_version": F.FACTOR_SET_VERSION,
        "kullanilan_surumler": kullanilan_surumler(db, facility_id),
    }


def belgeler(db: Session, facility_id: int) -> List[dict]:
    cikti = []
    for d in db.scalars(select(Document).where(
            Document.facility_id == facility_id).order_by(desc(Document.id))):
        satirlar = list(d.activities)
        cikti.append({
            "belge": d,
            "satir": len(satirlar),
            "bekleyen": sum(1 for a in satirlar if a.status == "onay_bekliyor"),
            "tco2e": round(sum((a.emission.co2e_kg / 1000.0)
                               for a in satirlar if a.emission), 3),
        })
    return cikti


def belge_detay(db: Session, document_id: int) -> Optional[dict]:
    d = db.get(Document, document_id)
    if d is None:
        return None
    return {"belge": d, "satirlar": sorted(d.activities, key=lambda a: a.id)}


def onay_kuyrugu(db: Session, facility_id: int) -> List[Activity]:
    return list(db.scalars(select(Activity).join(Document).where(
        Document.facility_id == facility_id,
        Activity.status == "onay_bekliyor").order_by(Activity.id)))


def bulgular(db: Session, facility_id: int) -> List[Finding]:
    sira = {"yuksek": 0, "uyari": 1, "bilgi": 2}
    liste = list(db.scalars(select(Finding).where(
        Finding.facility_id == facility_id, Finding.resolved == 0)))
    return sorted(liste, key=lambda f: (sira.get(f.severity, 3), f.id))


def olcumler(db: Session, facility_id: int) -> List[Measure]:
    return list(db.scalars(select(Measure).where(
        Measure.facility_id == facility_id).order_by(desc(Measure.tco2e_year))))


def tedarikciler(db: Session, facility_id: int) -> List[Supplier]:
    return list(db.scalars(select(Supplier).where(
        Supplier.facility_id == facility_id).order_by(Supplier.id)))


def iz_kayitlari(db: Session, limit: int = 200) -> List[AuditEvent]:
    return list(db.scalars(select(AuditEvent).order_by(
        desc(AuditEvent.id)).limit(limit)))


def son_rapor(db: Session, facility_id: int) -> Optional[Report]:
    return db.scalars(select(Report).where(
        Report.facility_id == facility_id).order_by(desc(Report.id))).first()


def envanter_csv(db: Session, facility_id: int) -> str:
    env = envanter(db, facility_id)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["faaliyet_id", "donem", "faktor", "miktar", "birim", "kapsam",
                "tCO2e", "faktor_duzeyi", "faktor_surumu", "formul"])
    for k in env["kalemler"]:
        w.writerow([k["activity_id"], csv_guvenli(k["period"]),
                    csv_guvenli(k["factor_key"]), k["value"],
                    csv_guvenli(k["unit"]), k["scope"], k["tco2e"],
                    csv_guvenli(k["tier"]), csv_guvenli(k.get("version", "")),
                    csv_guvenli(k["formula"])])
    w.writerow([])
    w.writerow(["Kapsam 1", env["scope1"]])
    w.writerow(["Kapsam 2", env["scope2"]])
    w.writerow(["Kapsam 3", env["scope3"]])
    w.writerow(["Toplam", env["toplam"]])
    return buf.getvalue()


def cbam_csv(db: Session, facility_id: int) -> str:
    """CBAM beyanı için ürün bazlı gömülü karbon veri seti."""
    tesis = db.get(Facility, facility_id)
    env = envanter(db, facility_id)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["alan", "deger", "birim", "kaynak"])
    if tesis is None:
        return buf.getvalue()
    w.writerow(["tesis", csv_guvenli(tesis.name), "", "kullanici"])
    w.writerow(["ulke", csv_guvenli(tesis.country), "", "kullanici"])
    w.writerow(["raporlama_yili", tesis.year, "", "kullanici"])
    w.writerow(["uretim", tesis.production_ton, "ton", "kullanici"])
    w.writerow(["ab_ihracat", tesis.export_ton_eu, "ton", "kullanici"])
    w.writerow(["dogrudan_emisyon", env["scope1"], "tCO2e", "hesaplanmis"])
    w.writerow(["dolayli_emisyon", env["scope2"], "tCO2e", "hesaplanmis"])
    w.writerow(["deger_zinciri", env["scope3"], "tCO2e", "hesaplanmis"])
    if tesis.production_ton > 0:
        d = calc.urun_birimine_dagit(env["scope1"], tesis.production_ton)
        i = calc.urun_birimine_dagit(env["scope2"], tesis.production_ton)
        w.writerow(["gomulu_dogrudan", d, "tCO2e/ton", "hesaplanmis"])
        w.writerow(["gomulu_dolayli", i, "tCO2e/ton", "hesaplanmis"])
        w.writerow(["gomulu_toplam", round(d + i, 6), "tCO2e/ton", "hesaplanmis"])
    surumler = kullanilan_surumler(db, facility_id) or [F.FACTOR_SET_VERSION]
    w.writerow(["faktor_surumu", ", ".join(surumler), "", "sistem"])
    w.writerow(["cerceve", "GHG Protocol / ISO 14064-1 / IPCC 2006", "", "sistem"])
    return buf.getvalue()


def raporlari_buda(db: Session, facility_id: int, en_fazla: int = 20) -> int:
    """Sınırsız büyümeyi önlemek için eski raporları siler.

    Denetim izi (AuditEvent) korunur — kanıt odur; rapor ise her zincir
    çalışmasında yeniden üretilebilir.
    """
    hepsi = list(db.scalars(select(Report).where(
        Report.facility_id == facility_id).order_by(desc(Report.id))))
    fazla = hepsi[en_fazla:]
    for r in fazla:
        db.delete(r)
    if fazla:
        db.commit()
    return len(fazla)
