"""Veri modeli — SQLAlchemy 2.0.

Tasarım ilkesi: hiçbir sayı kaynağından koparılmaz. Her emisyon kaydı,
geldiği faaliyet verisine; her faaliyet verisi, geldiği belge satırına bağlıdır.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (JSON, DateTime, Float, ForeignKey, Integer, String,
                        Text, create_engine)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, relationship,
                            sessionmaker)

from .config import DATABASE_URL


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Facility(Base):
    """Tesis — hesabın yapıldığı işletme."""

    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(2), default="TR")
    sector: Mapped[str] = mapped_column(String(120), default="")
    production_ton: Mapped[float] = mapped_column(Float, default=0.0)
    export_ton_eu: Mapped[float] = mapped_column(Float, default=0.0)
    year: Mapped[int] = mapped_column(Integer, default=2026)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)

    documents: Mapped[list["Document"]] = relationship(back_populates="facility",
                                                       cascade="all, delete-orphan")
    suppliers: Mapped[list["Supplier"]] = relationship(back_populates="facility",
                                                       cascade="all, delete-orphan")
    measures: Mapped[list["Measure"]] = relationship(back_populates="facility",
                                                     cascade="all, delete-orphan")


class Document(Base):
    """Yüklenen belge — fatura, irsaliye, sayaç çıktısı."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"))
    filename: Mapped[str] = mapped_column(String(300))
    doc_type: Mapped[str] = mapped_column(String(40), default="fatura")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="islendi")
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    extractor: Mapped[str] = mapped_column(String(40), default="kural")
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)

    facility: Mapped[Facility] = relationship(back_populates="documents")
    activities: Mapped[list["Activity"]] = relationship(back_populates="document",
                                                        cascade="all, delete-orphan")


class Activity(Base):
    """Belgeden çıkarılan tek bir faaliyet verisi satırı."""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    factor_key: Mapped[str] = mapped_column(String(60))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    period: Mapped[str] = mapped_column(String(20), default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(30), default="onayli")
    source_line: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    note_code: Mapped[str] = mapped_column(String(60), default="")
    note_params: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)

    document: Mapped[Document] = relationship(back_populates="activities")
    emission: Mapped[Optional["Emission"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan", uselist=False)


class Emission(Base):
    """Hesaplanmış emisyon — formülü ve faktör sürümüyle birlikte."""

    __tablename__ = "emissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), unique=True)
    scope: Mapped[int] = mapped_column(Integer)
    co2e_kg: Mapped[float] = mapped_column(Float)
    energy_gj: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    factor_version: Mapped[str] = mapped_column(String(20))
    factor_tier: Mapped[str] = mapped_column(String(20), default="ipcc")
    factor_source: Mapped[str] = mapped_column(Text, default="")
    formula: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list] = mapped_column(JSON, default=list)
    calculated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)

    activity: Mapped[Activity] = relationship(back_populates="emission")


class Finding(Base):
    """Denetim ajanının bulduğu tutarsızlık ya da anomali."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"))
    activity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("activities.id"),
                                                       nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="uyari")
    code: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Supplier(Base):
    """Kapsam 3 verisi için takip edilen tedarikçi."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"))
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), default="")
    material: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(30), default="bekliyor")
    requested_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    responded_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    reported_kgco2e_per_unit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    factor_key: Mapped[str] = mapped_column(String(60), default="")
    last_reminder_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)

    facility: Mapped[Facility] = relationship(back_populates="suppliers")


class Measure(Base):
    """Azaltım önlemi — tCO2e, yatırım ve geri ödeme ile."""

    __tablename__ = "measures"

    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"))
    code: Mapped[str] = mapped_column(String(40), default="")
    name: Mapped[str] = mapped_column(String(200))
    basis_params: Mapped[dict] = mapped_column(JSON, default=dict)
    tco2e_year: Mapped[float] = mapped_column(Float, default=0.0)
    capex_try: Mapped[float] = mapped_column(Float, default=0.0)
    saving_try_year: Mapped[float] = mapped_column(Float, default=0.0)
    payback_years: Mapped[float] = mapped_column(Float, default=0.0)
    basis: Mapped[str] = mapped_column(Text, default="")
    selected: Mapped[int] = mapped_column(Integer, default=0)

    facility: Mapped[Facility] = relationship(back_populates="measures")


class Report(Base):
    """Üretilen uyum raporu (CBAM / TR ETS)."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"))
    kind: Mapped[str] = mapped_column(String(20))
    period: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Setting(Base):
    """Arayüzden değiştirilebilen ayar.

    Öncelik: veri tabanı > ortam değişkeni > koddaki varsayılan. Böylece
    sunucuya erişimi olmayan kullanıcı da API anahtarını girebilir, ama
    ortam değişkeniyle kurulan dağıtım da bozulmaz.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True),
                                                    default=now, onupdate=now)


class AuditEvent(Base):
    """Denetim izi — kim, neyi, ne zaman değiştirdi."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    actor: Mapped[str] = mapped_column(String(60), default="sistem")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


_motor_ayar = {"echo": False, "future": True, "pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    # SQLite'ta havuz doğrulaması gereksiz, iş parçacığı kontrolü ise engeldir.
    _motor_ayar.pop("pool_pre_ping")
    _motor_ayar["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_motor_ayar)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Sürüm yükseltmelerinde eklenen sütunlar. create_all yalnızca eksik TABLO
# yaratır, var olan tabloya sütun eklemez; bu yüzden elle tamamlıyoruz.
EK_SUTUNLAR = {
    "documents": {"content_hash": "VARCHAR(64) DEFAULT ''"},
    "findings": {"params": "TEXT DEFAULT '{}'"},
    "activities": {"note_code": "VARCHAR(60) DEFAULT ''",
                   "note_params": "TEXT DEFAULT '{}'"},
    "measures": {"code": "VARCHAR(40) DEFAULT ''",
                 "basis_params": "TEXT DEFAULT '{}'"},
    "suppliers": {
        "factor_key": "VARCHAR(60) DEFAULT ''",
        "last_reminder_at": "TIMESTAMP NULL",
        "reminder_count": "INTEGER DEFAULT 0",
    },
}


def _eksik_sutunlari_ekle() -> list[str]:
    """Var olan veri tabanını yeni sürüme uyarlar."""
    from sqlalchemy import inspect, text

    eklenen = []
    denetci = inspect(engine)
    mevcut_tablolar = set(denetci.get_table_names())
    with engine.begin() as baglanti:
        for tablo, sutunlar in EK_SUTUNLAR.items():
            if tablo not in mevcut_tablolar:
                continue
            var_olan = {s["name"] for s in denetci.get_columns(tablo)}
            for ad, tanim in sutunlar.items():
                if ad in var_olan:
                    continue
                try:
                    baglanti.execute(
                        text(f"ALTER TABLE {tablo} ADD COLUMN {ad} {tanim}"))
                    eklenen.append(f"{tablo}.{ad}")
                except Exception:
                    pass
    return eklenen


def init_db() -> None:
    Base.metadata.create_all(engine)
    _eksik_sutunlari_ekle()


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
