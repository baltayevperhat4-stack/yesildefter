"""Demo veri üreteci — modellenmiş örnek tesis.

Gerçek bir tesisin verisi değildir. Jüriye ve pilota gösterilecek uçtan uca
akışı çalıştırmak için üretilmiş, varsayımları açıkça yazılmış örnektir.

Çalıştırma:  python -m seed.demo
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.agents import orchestrator
from app.agents.document_agent import metin_oku
from app.config import UPLOAD_DIR
from app.models import (Activity, AuditEvent, Document, Emission, Facility,
                        Finding, Measure, Report, SessionLocal, Supplier,
                        init_db)

ORNEK_DIR = Path(__file__).parent / "samples"

AYLAR = ["01", "02", "03", "04", "05", "06",
         "07", "08", "09", "10", "11", "12"]

# Yıllık doğal gaz 1.000.000 m3, mevsimsel dağılım (toplam 1.000)
GAZ_PAY = [118, 112, 101, 83, 68, 58, 55, 57, 67, 82, 94, 105]
# Yıllık elektrik 4.500.000 kWh (toplam 1.000)
ELK_PAY = [86, 82, 85, 83, 84, 80, 78, 76, 83, 85, 88, 90]

GAZ_YILLIK = 1_000_000.0
ELK_YILLIK = 4_500_000.0

TESIS = dict(
    name="Örnek Döküm ve Metal İşleme A.Ş. (modellenmiş)",
    country="TR",
    sector="Demir-çelik döküm · CBAM kapsamında ürün",
    production_ton=2894.0,
    export_ton_eu=742.0,
    year=2027,
)

TEDARIKCILER = [
    ("Ege Hurda Metal Ltd.", "tedarik@ornek-ege.example", "Hurda çelik",
     "hurda_celik"),
    ("Marmara Refrakter San.", "satis@ornek-refrakter.example",
     "Refrakter tuğla", ""),
    ("Anadolu Lojistik A.Ş.", "info@ornek-lojistik.example", "Karayolu taşıma",
     "karayolu_tasima"),
    ("Trakya Alüminyum", "cevre@ornek-aluminyum.example", "Hurda alüminyum",
     "hurda_alum"),
]


def _gaz_fatura(ay: str, m3: float, birim: str = "m3") -> str:
    """birim='kg' verildiğinde, gerçek hayatta sık görülen birim hatası
    simüle edilir: belge ajanı bunu yakalar ve satırı onay kuyruğuna düşürür."""
    tutar = m3 * 7.4
    return f"""ÖRNEK DOĞALGAZ DAĞITIM A.Ş.
Fatura No: DG-2027{ay}-004512
Fatura Tarihi: 05.{ay}.2027
Abone: Örnek Döküm ve Metal İşleme A.Ş. - Tesis 1
Tüketim Dönemi: 01.{ay}.2027 - 28.{ay}.2027

Açıklama                         Miktar        Birim      Tutar (TL)
--------------------------------------------------------------------
Doğal gaz tüketimi             {m3:>10,.0f}        {birim:<6} {tutar:>12,.2f}
Sistem kullanım bedeli                                       1 480,00
--------------------------------------------------------------------
Ödenecek Tutar                                          {tutar + 1480:>12,.2f}
""".replace(",", " ")


def _elektrik_fatura(ay: str, kwh: float) -> str:
    tutar = kwh * 2.35
    return f"""ÖRNEK ELEKTRİK PERAKENDE SATIŞ A.Ş.
Fatura No: EL-2027{ay}-99134
Fatura Tarihi: 07.{ay}.2027
Tesisat No: 40219883   Abone: Örnek Döküm ve Metal İşleme A.Ş.
Okuma Dönemi: 01.{ay}.2027 - 28.{ay}.2027

Kalem                             Miktar       Birim      Tutar (TL)
--------------------------------------------------------------------
Aktif enerji tüketimi          {kwh:>10,.0f}       kWh     {tutar:>12,.2f}
Dağıtım bedeli                                               9 120,00
--------------------------------------------------------------------
Toplam                                                  {tutar + 9120:>12,.2f}
""".replace(",", " ")


def _hurda_irsaliye(ceyrek: int, ay: str, ton: float) -> str:
    return f"""EGE HURDA METAL LTD. ŞTİ.
Sevk İrsaliyesi No: SI-2027-{ceyrek:02d}-771
Tarih: 15.{ay}.2027
Alıcı: Örnek Döküm ve Metal İşleme A.Ş.

Malzeme                            Miktar      Birim
-----------------------------------------------------
Hurda çelik (DKP + sac)          {ton:>9,.1f}       ton
Karayolu taşıma                {ton * 180:>11,.0f}   ton-km
""".replace(",", " ")


def _motorin_fatura(ay: str, litre: float) -> str:
    return f"""ÖRNEK AKARYAKIT A.Ş.
Fatura No: AK-2027{ay}-233
Tarih: 20.{ay}.2027
Müşteri: Örnek Döküm ve Metal İşleme A.Ş. (forklift ve jeneratör)

Ürün                               Miktar     Birim    Tutar (TL)
------------------------------------------------------------------
Motorin (dizel)                  {litre:>9,.0f}        lt    {litre * 44.5:>11,.2f}
""".replace(",", " ")


def ornekleri_uret() -> list[Path]:
    """Örnek belgeleri diske yazar ve yollarını döndürür."""
    ORNEK_DIR.mkdir(parents=True, exist_ok=True)
    for eski in ORNEK_DIR.glob("*.txt"):
        eski.unlink()

    yollar: list[Path] = []
    for i, ay in enumerate(AYLAR):
        m3 = GAZ_YILLIK * GAZ_PAY[i] / sum(GAZ_PAY)
        # Temmuz faturasında birim yanlış basılmış: ajanın onay kuyruğuna
        # düşürmesi beklenen gerçekçi hata.
        birim = "kg" if ay == "07" else "m3"
        p = ORNEK_DIR / f"dogalgaz_2027-{ay}.txt"
        p.write_text(_gaz_fatura(ay, m3, birim), encoding="utf-8")
        yollar.append(p)

        kwh = ELK_YILLIK * ELK_PAY[i] / sum(ELK_PAY)
        p = ORNEK_DIR / f"elektrik_2027-{ay}.txt"
        p.write_text(_elektrik_fatura(ay, kwh), encoding="utf-8")
        yollar.append(p)

    for c, (ay, ton) in enumerate(
            [("03", 760.0), ("06", 735.0), ("09", 745.0), ("12", 760.0)], start=1):
        p = ORNEK_DIR / f"hurda_celik_2027-{ay}.txt"
        p.write_text(_hurda_irsaliye(c, ay, ton), encoding="utf-8")
        yollar.append(p)

    for ay, lt in [("04", 4200.0), ("10", 4600.0)]:
        p = ORNEK_DIR / f"motorin_2027-{ay}.txt"
        p.write_text(_motorin_fatura(ay, lt), encoding="utf-8")
        yollar.append(p)

    return yollar


def temizle(db) -> None:
    for model in (Emission, Activity, Document, Finding, Measure, Report,
                  Supplier, AuditEvent, Facility):
        for satir in db.query(model).all():
            db.delete(satir)
    db.commit()


def yukle(sifirla: bool = True) -> dict:
    """Demo tesisi kurar, belgeleri işler ve ajan zincirini çalıştırır."""
    init_db()
    db = SessionLocal()
    try:
        if sifirla:
            temizle(db)

        tesis = Facility(**TESIS)
        db.add(tesis)
        db.flush()

        for ad, eposta, malzeme, fkey in TEDARIKCILER:
            db.add(Supplier(facility_id=tesis.id, name=ad, email=eposta,
                            material=malzeme, factor_key=fkey))
        db.flush()

        yollar = ornekleri_uret()
        for yol in yollar:
            hedef = UPLOAD_DIR / yol.name
            shutil.copyfile(yol, hedef)
            metin = metin_oku(hedef)
            import hashlib
            ozet = hashlib.sha256(hedef.read_bytes()).hexdigest()
            belge = Document(facility_id=tesis.id, filename=yol.name,
                             doc_type="fatura", raw_text=metin,
                             content_hash=ozet)
            db.add(belge)
            db.flush()
            orchestrator.belge_isle(db, belge.id)
        db.commit()

        sonuclar = orchestrator.zinciri_calistir(db, tesis.id)
        return {"facility_id": tesis.id, "belge": len(yollar),
                "zincir": sonuclar}
    finally:
        db.close()


if __name__ == "__main__":
    ozet = yukle()
    print(f"Tesis #{ozet['facility_id']} · {ozet['belge']} belge işlendi")
    for adim in ozet["zincir"]:
        isaret = "✓" if adim["ok"] else "✗"
        print(f"  {isaret} {adim['agent']:<16} {adim['summary']}")
