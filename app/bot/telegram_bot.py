"""Telegram botu — sahadan belge göndermek ve onay vermek için.

KOBİ'de karbon verisini toplayan kişi genelde masa başında değildir. Bot,
faturayı telefondan göndermeyi ve onay kuyruğundaki satırı tek dokunuşla
onaylamayı sağlar; arka planda aynı ajan zinciri çalışır.

Çalıştırma:
    TELEGRAM_BOT_TOKEN=... python -m app.bot.telegram_bot

Token yoksa bot başlamaz, uygulamanın geri kalanı etkilenmez.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from ..agents import orchestrator
from ..agents.document_agent import metin_oku
from .. import settings_store as A
from ..config import UPLOAD_DIR
from ..models import Activity, Document, SessionLocal, init_db
from ..services import aktif_tesis, onay_kuyrugu, pano

API = "https://api.telegram.org/bot{token}/{metot}"
DOSYA = "https://api.telegram.org/file/bot{token}/{yol}"
IZIN_VERILEN = {".pdf", ".csv", ".tsv", ".txt"}

YARDIM = (
    "YeşilDefter botu\n\n"
    "/ozet — envanter özeti\n"
    "/onay — onay bekleyen satırlar\n"
    "/rapor — CBAM veri setini gönder\n\n"
    "Fatura, irsaliye ya da sayaç çıktısını (PDF, CSV, TXT) doğrudan "
    "gönderebilirsiniz; sistem okur, hesaplar ve sonucu yazar."
)


# ------------------------------------------------------------ mesaj kurucular
def ozet_metni(db) -> str:
    tesis = aktif_tesis(db)
    if tesis is None:
        return "Henüz tesis tanımlı değil. Web arayüzünden tesis ekleyin."
    p = pano(db, tesis.id)
    e = p["envanter"]
    satir = [
        f"*{tesis.name}* · {tesis.year}",
        f"Kapsam 1: {e['scope1']:,.1f} tCO2e",
        f"Kapsam 2: {e['scope2']:,.1f} tCO2e",
        f"Kapsam 3: {e['scope3']:,.1f} tCO2e",
        f"Toplam: {e['toplam']:,.1f} tCO2e",
    ]
    if p["gomulu"]:
        satir.append(f"Gömülü karbon: {p['gomulu']['toplam']:,.3f} tCO2e/ton")
    if p["kacinilan"]:
        satir.append(
            f"Kaçınılan CBAM maliyeti: {p['kacinilan']['kacinilan_eur']:,.0f} €/yıl")
    satir.append(f"Onay bekleyen: {p['bekleyen']} · Bulgu: {p['bulgu_sayi']}")
    satir.append(f"Azaltım: {p['azaltim_tco2e']:,.0f} tCO2e/yıl")
    return "\n".join(satir).replace(",", " ")


def onay_satiri(a: Activity) -> str:
    return (f"#{a.id} · {a.factor_key} · {a.value:,.1f} {a.unit} · "
            f"güven %{a.confidence * 100:.0f}\n{a.source_line[:120]}"
            ).replace(",", " ")


def onay_klavyesi(a: Activity) -> Dict[str, Any]:
    return {"inline_keyboard": [[
        {"text": "✓ Onayla", "callback_data": f"ok:{a.id}"},
        {"text": "✗ Reddet", "callback_data": f"no:{a.id}"},
    ]]}


# --------------------------------------------------------------- API sarmalı
class Bot:
    def __init__(self, token: str):
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN tanımlı değil")
        self.token = token
        self.offset: Optional[int] = None
        self.http = httpx.Client(timeout=65.0)

    def cagir(self, metot: str, **veri) -> dict:
        r = self.http.post(API.format(token=self.token, metot=metot), json=veri)
        r.raise_for_status()
        return r.json()

    def yaz(self, chat_id: int, metin: str, klavye: dict | None = None) -> None:
        veri: Dict[str, Any] = {"chat_id": chat_id, "text": metin,
                                "parse_mode": "Markdown"}
        if klavye:
            veri["reply_markup"] = klavye
        try:
            self.cagir("sendMessage", **veri)
        except Exception:
            veri.pop("parse_mode", None)
            self.cagir("sendMessage", **veri)

    def belge_gonder(self, chat_id: int, ad: str, icerik: bytes) -> None:
        r = self.http.post(
            API.format(token=self.token, metot="sendDocument"),
            data={"chat_id": str(chat_id)},
            files={"document": (ad, icerik, "application/octet-stream")},
        )
        r.raise_for_status()

    def dosya_indir(self, file_id: str) -> Optional[bytes]:
        bilgi = self.cagir("getFile", file_id=file_id)
        yol = bilgi.get("result", {}).get("file_path")
        if not yol:
            return None
        r = self.http.get(DOSYA.format(token=self.token, yol=yol))
        r.raise_for_status()
        return r.content

    # ----------------------------------------------------------- iş mantığı
    def yetkili(self, chat_id: int) -> bool:
        """Yalnızca TELEGRAM_ALLOWED_CHATS içindeki sohbetler işlem yapabilir.

        Liste boşsa bot hiçbir isteğe yanıt vermez: açık bir bot, tesisin tüm
        envanterini ve onay yetkisini herkese açardı."""
        return chat_id in A.telegram_ayarlari()["izinli"]

    def komut(self, chat_id: int, metin: str) -> None:
        db = SessionLocal()
        try:
            if metin.startswith("/start") or metin.startswith("/yardim"):
                self.yaz(chat_id, YARDIM)
            elif metin.startswith("/ozet"):
                self.yaz(chat_id, ozet_metni(db))
            elif metin.startswith("/onay"):
                tesis = aktif_tesis(db)
                kuyruk: List[Activity] = (onay_kuyrugu(db, tesis.id)
                                          if tesis else [])
                if not kuyruk:
                    self.yaz(chat_id, "Onay bekleyen satır yok.")
                for a in kuyruk[:10]:
                    self.yaz(chat_id, onay_satiri(a), onay_klavyesi(a))
            elif metin.startswith("/rapor"):
                tesis = aktif_tesis(db)
                if tesis is None:
                    self.yaz(chat_id, "Tesis yok.")
                else:
                    from ..services import cbam_csv
                    self.belge_gonder(chat_id, "cbam_veri_seti.csv",
                                      cbam_csv(db, tesis.id).encode("utf-8"))
            else:
                self.yaz(chat_id, YARDIM)
        finally:
            db.close()

    def belge(self, chat_id: int, file_id: str, dosya_adi: str) -> None:
        son = Path(dosya_adi or "").suffix.lower()
        if son not in IZIN_VERILEN:
            self.yaz(chat_id,
                     f"Desteklenmeyen biçim: {son or '?'}. "
                     f"PDF, CSV ya da TXT gönderin.")
            return
        icerik = self.dosya_indir(file_id)
        if not icerik:
            self.yaz(chat_id, "Dosya indirilemedi.")
            return

        db = SessionLocal()
        try:
            tesis = aktif_tesis(db)
            if tesis is None:
                self.yaz(chat_id, "Önce web arayüzünden tesis tanımlayın.")
                return
            from ..main import guvenli_dosya_adi
            hedef = UPLOAD_DIR / guvenli_dosya_adi(dosya_adi)
            hedef.write_bytes(icerik)
            belge = Document(facility_id=tesis.id, filename=hedef.name,
                             raw_text=metin_oku(hedef))
            db.add(belge)
            db.flush()
            sonuc = orchestrator.belge_isle(db, belge.id)
            db.commit()
            orchestrator.zinciri_calistir(db, tesis.id)

            self.yaz(chat_id, f"*{hedef.name}*\n{sonuc.summary}")
            kuyruk = onay_kuyrugu(db, tesis.id)
            for a in kuyruk[:5]:
                self.yaz(chat_id, onay_satiri(a), onay_klavyesi(a))
            self.yaz(chat_id, ozet_metni(db))
        finally:
            db.close()

    def geri_cagri(self, chat_id: int, veri: str, callback_id: str) -> None:
        karar, _, ham_id = veri.partition(":")
        if karar not in ("ok", "no"):
            self.cagir("answerCallbackQuery", callback_query_id=callback_id,
                       text="Geçersiz işlem")
            return
        db = SessionLocal()
        try:
            a = db.get(Activity, int(ham_id)) if ham_id.isdigit() else None
            if a is None:
                self.cagir("answerCallbackQuery", callback_query_id=callback_id,
                           text="Satır bulunamadı")
                return
            a.status = "onayli" if karar == "ok" else "reddedildi"
            db.commit()
            orchestrator.zinciri_calistir(db, a.document.facility_id)
            self.cagir("answerCallbackQuery", callback_query_id=callback_id,
                       text="Onaylandı" if karar == "ok" else "Reddedildi")
            self.yaz(chat_id,
                     f"#{a.id} {'onaylandı' if karar == 'ok' else 'reddedildi'}.\n\n"
                     + ozet_metni(db))
        finally:
            db.close()

    # ------------------------------------------------------------- ana döngü
    def calistir(self) -> None:
        init_db()
        print("YeşilDefter Telegram botu çalışıyor…")
        while True:
            try:
                cevap = self.cagir("getUpdates", offset=self.offset, timeout=50)
            except Exception as exc:
                print("getUpdates hatası:", exc)
                time.sleep(3)
                continue
            for g in cevap.get("result", []):
                self.offset = g["update_id"] + 1
                try:
                    self.guncelleme(g)
                except Exception as exc:         # tek mesaj botu düşürmesin
                    print("güncelleme hatası:", exc)

    def guncelleme(self, g: dict) -> None:
        if "callback_query" in g:
            cq = g["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            if not self.yetkili(chat_id):
                self.cagir("answerCallbackQuery", callback_query_id=cq["id"],
                           text="Yetkiniz yok")
                return
            self.geri_cagri(chat_id, cq.get("data", ""), cq["id"])
            return
        mesaj = g.get("message") or g.get("edited_message")
        if not mesaj:
            return
        chat_id = mesaj["chat"]["id"]
        if not self.yetkili(chat_id):
            self.yaz(chat_id,
                     "Bu bot yalnızca yetkili kullanıcılara açıktır. "
                     f"Sohbet kimliğiniz: {chat_id}")
            return
        if "document" in mesaj:
            d = mesaj["document"]
            self.belge(chat_id, d["file_id"], d.get("file_name", "belge.pdf"))
        elif "text" in mesaj:
            self.komut(chat_id, mesaj["text"].strip())


def main() -> None:
    init_db()
    jeton = A.telegram_ayarlari()["token"]
    if not jeton:
        print("Telegram jetonu tanımlı değil (ayarlar sayfası ya da "
              "TELEGRAM_BOT_TOKEN); bot başlatılmadı.")
        return
    if not A.telegram_ayarlari()["izinli"]:
        print("UYARI: yetkili sohbet listesi boş — bot hiçbir isteğe yanıt "
              "vermeyecek. Ayarlar sayfasından sohbet kimliğinizi ekleyin.")
    Bot(jeton).calistir()


if __name__ == "__main__":
    main()
