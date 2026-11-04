"""Rapor üretimi — XLSX ve PDF.

Rapor, doğrulayıcıya verilecek belgedir: envanter, ürün bazlı dağıtım, faktör
kaynakları ve denetim notları tek dosyada toplanır.
"""

from __future__ import annotations

import datetime as dt
import io
from typing import Optional

from sqlalchemy.orm import Session

from ..agents.compliance_agent import envanter
from .. import settings_store as A
from ..core import calc
from ..core import factors as F
from ..core.util import temiz_metin
from ..models import Facility, Finding, Measure


def _tesis_ozet(db: Session, facility_id: int):
    tesis = db.get(Facility, facility_id)
    env = envanter(db, facility_id)
    gomulu = None
    kacinilan = None
    if tesis and tesis.production_ton > 0:
        d = calc.urun_birimine_dagit(env["scope1"], tesis.production_ton)
        i = calc.urun_birimine_dagit(env["scope2"], tesis.production_ton)
        gomulu = {"dogrudan": d, "dolayli": i, "toplam": round(d + i, 6)}
        if tesis.export_ton_eu > 0:
            kacinilan = calc.kacinilan_maliyet(
                gomulu["toplam"] * tesis.export_ton_eu, tesis.year, A.cbam_eur(db))
    return tesis, env, gomulu, kacinilan


def xlsx(db: Session, facility_id: int) -> bytes:
    """Çok sayfalı Excel raporu döndürür."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    tesis, env, gomulu, kacinilan = _tesis_ozet(db, facility_id)
    wb = Workbook()
    baslik_font = Font(bold=True, color="FFFFFF")
    baslik_dolgu = PatternFill("solid", fgColor="1F7A5A")

    def yaz(ws, satir):
        """Her hücreyi openpyxl'in kabul ettiği biçime indirger.

        Belgeden gelen denetim karakterleri (\x00 vb.) openpyxl'i çökertir;
        bu yüzden metin hücreleri temizlenir."""
        ws.append([h if isinstance(h, (int, float)) else temiz_metin(h, 2000)
                   for h in satir])

    def basliklandir(ws, basliklar):
        ws.append(basliklar)
        for h in ws[1]:
            h.font = baslik_font
            h.fill = baslik_dolgu
            h.alignment = Alignment(vertical="center")

    # 1 — Özet
    ws = wb.active
    ws.title = "Özet"
    basliklandir(ws, ["Alan", "Değer", "Birim"])
    satirlar = [
        ("Tesis", tesis.name if tesis else "—", ""),
        ("Raporlama yılı", tesis.year if tesis else "", ""),
        ("Üretim", tesis.production_ton if tesis else 0, "ton"),
        ("AB'ye ihracat", tesis.export_ton_eu if tesis else 0, "ton"),
        ("Kapsam 1", env["scope1"], "tCO2e"),
        ("Kapsam 2", env["scope2"], "tCO2e"),
        ("Kapsam 3", env["scope3"], "tCO2e"),
        ("Toplam", env["toplam"], "tCO2e"),
    ]
    if gomulu:
        satirlar += [
            ("Gömülü karbon — doğrudan", gomulu["dogrudan"], "tCO2e/ton"),
            ("Gömülü karbon — dolaylı", gomulu["dolayli"], "tCO2e/ton"),
            ("Gömülü karbon — toplam", gomulu["toplam"], "tCO2e/ton"),
        ]
    if kacinilan:
        satirlar += [
            ("İhracatın gömülü karbonu", kacinilan["gomulu_tco2e"], "tCO2e"),
            ("CBAM marjı", kacinilan["marj"], "oran"),
            ("Kaçınılan maliyet", kacinilan["kacinilan_eur"], "EUR/yıl"),
        ]
    satirlar += [
        ("Faktör sürümü", F.FACTOR_SET_VERSION, ""),
        ("Çerçeve", "GHG Protocol / ISO 14064-1 / IPCC 2006", ""),
        ("Üretildi", dt.datetime.now().strftime("%Y-%m-%d %H:%M"), ""),
    ]
    for s in satirlar:
        yaz(ws, list(s))
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 44
    ws.column_dimensions["C"].width = 12

    # 2 — Envanter satırları
    ws2 = wb.create_sheet("Envanter")
    basliklandir(ws2, ["Faaliyet ID", "Dönem", "Faktör", "Miktar", "Birim",
                       "Kapsam", "tCO2e", "Faktör düzeyi", "Formül"])
    for k in env["kalemler"]:
        yaz(ws2, [k["activity_id"], k["period"], k["factor_key"], k["value"],
                  k["unit"], k["scope"], k["tco2e"], k["tier"], k["formula"]])
    for sutun, genislik in zip("ABCDEFGHI", (12, 11, 18, 14, 9, 9, 12, 14, 70)):
        ws2.column_dimensions[sutun].width = genislik

    # 3 — Faktörler
    ws3 = wb.create_sheet("Faktörler")
    basliklandir(ws3, ["Anahtar", "Ad", "Kapsam", "Birim", "Değer", "Düzey",
                       "Kaynak"])
    for f in F.all_factors():
        deger = (f"{f['ncv_mj_per_unit']} MJ/{f['unit']}; "
                 f"{f['co2_kg_per_gj']} kgCO2/GJ") if f["type"] == "fuel" else \
            f"{f['kgco2e_per_unit']} kgCO2e/{f['unit']}"
        yaz(ws3, [f["key"], f["name_tr"], f["scope"], f["unit"], deger,
                  f["tier"], f["source"]])
    for sutun, genislik in zip("ABCDEFG", (18, 30, 9, 10, 34, 12, 60)):
        ws3.column_dimensions[sutun].width = genislik

    # 4 — Denetim bulguları
    ws4 = wb.create_sheet("Bulgular")
    basliklandir(ws4, ["Öncelik", "Kod", "Açıklama"])
    for b in db.query(Finding).filter(Finding.facility_id == facility_id,
                                      Finding.resolved == 0).all():
        yaz(ws4, [b.severity, b.code, b.message])
    for sutun, genislik in zip("ABC", (12, 22, 100)):
        ws4.column_dimensions[sutun].width = genislik

    # 5 — Azaltım
    ws5 = wb.create_sheet("Azaltım")
    basliklandir(ws5, ["Önlem", "tCO2e/yıl", "Yatırım (TL)", "Tasarruf (TL/yıl)",
                       "Geri ödeme (yıl)", "Dayanak"])
    for m in db.query(Measure).filter(Measure.facility_id == facility_id).all():
        yaz(ws5, [m.name, m.tco2e_year, m.capex_try, m.saving_try_year,
                  m.payback_years, m.basis])
    for sutun, genislik in zip("ABCDEF", (46, 13, 16, 18, 16, 70)):
        ws5.column_dimensions[sutun].width = genislik

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def pdf(db: Session, facility_id: int) -> bytes:
    """Tek sayfalık özet PDF."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    tesis, env, gomulu, kacinilan = _tesis_ozet(db, facility_id)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm,
                            bottomMargin=18 * mm, leftMargin=18 * mm,
                            rightMargin=18 * mm, title="YesilDefter raporu")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=16, spaceAfter=4)
    alt = ParagraphStyle("alt", parent=ss["Normal"], fontSize=9,
                         textColor=colors.HexColor("#555555"), spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11, spaceBefore=10,
                        spaceAfter=4)
    kucuk = ParagraphStyle("kucuk", parent=ss["Normal"], fontSize=8,
                           textColor=colors.HexColor("#666666"))

    ak = []
    ak.append(Paragraph("YesilDefter — Karbon Envanteri Raporu", h1))
    ak.append(Paragraph(
        f"{tesis.name if tesis else '-'} &middot; {tesis.year if tesis else ''} "
        f"&middot; faktor surumu {F.FACTOR_SET_VERSION}", alt))

    def tablo(veri, genislikler):
        t = Table(veri, colWidths=genislikler)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F7A5A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    ak.append(Paragraph("Envanter", h2))
    ak.append(tablo([
        ["Kapsam", "tCO2e"],
        ["Kapsam 1 - dogrudan yakit", f"{env['scope1']:,.1f}"],
        ["Kapsam 2 - satin alinan enerji", f"{env['scope2']:,.1f}"],
        ["Kapsam 3 - deger zinciri", f"{env['scope3']:,.1f}"],
        ["Toplam", f"{env['toplam']:,.1f}"],
    ], [110 * mm, 55 * mm]))

    if gomulu:
        ak.append(Paragraph("Urun birimine dagitim", h2))
        ak.append(tablo([
            ["Kalem", "tCO2e/ton"],
            ["Dogrudan", f"{gomulu['dogrudan']:,.3f}"],
            ["Dolayli", f"{gomulu['dolayli']:,.3f}"],
            ["Toplam gomulu karbon", f"{gomulu['toplam']:,.3f}"],
        ], [110 * mm, 55 * mm]))

    if kacinilan:
        ak.append(Paragraph("CBAM", h2))
        ak.append(tablo([
            ["Kalem", "Deger"],
            ["Ihracatin gomulu karbonu", f"{kacinilan['gomulu_tco2e']:,.1f} tCO2e"],
            ["Marj", f"{kacinilan['marj']:.0%}"],
            ["Sertifika fiyati (varsayim)", f"{kacinilan['sertifika_eur']:,.0f} EUR"],
            ["Kacinilan maliyet", f"{kacinilan['kacinilan_eur']:,.0f} EUR/yil"],
        ], [110 * mm, 55 * mm]))

    onlemler = db.query(Measure).filter(Measure.facility_id == facility_id).all()
    if onlemler:
        ak.append(Paragraph("Azaltim onlemleri", h2))
        veri = [["Onlem", "tCO2e/yil", "Geri odeme"]]
        for m in onlemler:
            veri.append([temiz_metin(m.name, 58), f"{m.tco2e_year:,.1f}",
                         f"{m.payback_years:,.2f} yil"])
        ak.append(tablo(veri, [105 * mm, 30 * mm, 30 * mm]))

    ak.append(Spacer(1, 10))
    ak.append(Paragraph(
        "Hesaplama cercevesi: GHG Protocol, ISO 14064-1, IPCC 2006. "
        "Varsayim tabanli faktorler dogrulama oncesi ulusal veriyle "
        "degistirilmelidir. Sayisal sonuclar modellenmis ornek tesise aittir.",
        kucuk))

    doc.build(ak)
    return buf.getvalue()
