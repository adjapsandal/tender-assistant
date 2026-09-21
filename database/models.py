from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(100))
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="users")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text)
    inn: Mapped[str | None] = mapped_column(String(20))
    kpp: Mapped[str | None] = mapped_column(String(20))
    ogrn: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    director: Mapped[str | None] = mapped_column(String(255))
    experience: Mapped[str | None] = mapped_column(Text)
    stack: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    users: Mapped[list["User"]] = relationship("User", back_populates="company", cascade="all, delete-orphan")
    skus: Mapped[list["SKU"]] = relationship("SKU", back_populates="company", cascade="all, delete-orphan")
    tenders: Mapped[list["Tender"]] = relationship("Tender", back_populates="company", cascade="all, delete-orphan")
    templates: Mapped[list["DocumentTemplate"]] = relationship(
        "DocumentTemplate", back_populates="company", cascade="all, delete-orphan"
    )
    won_tenders: Mapped[list["WonTender"]] = relationship(
        "WonTender", back_populates="company", cascade="all, delete-orphan"
    )
    web_users: Mapped[list["WebUser"]] = relationship("WebUser", back_populates="company", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name='{self.name}')>"


class SKU(Base):
    """Товары/услуги компании (ранее search_presets)."""

    __tablename__ = "skus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # "БАНОЧКИ для анализов"
    description: Mapped[str | None] = mapped_column(Text)  # Описание для КП
    keywords: Mapped[str] = mapped_column(Text, nullable=False)  # Продвинутый синтаксис для rostender
    exceptions: Mapped[str | None] = mapped_column(Text)  # Исключения для поиска
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="skus")

    def __repr__(self) -> str:
        return f"<SKU(id={self.id}, name='{self.name}')>"


class Tender(Base):
    __tablename__ = "tenders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    tender_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    customer: Mapped[str | None] = mapped_column(String(500))
    price: Mapped[str | None] = mapped_column(String(100))
    deadline: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(1000))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    embedding_has_files: Mapped[bool] = mapped_column(Boolean, default=False)
    relevance_score: Mapped[float | None] = mapped_column(Float)  # 0-100
    category: Mapped[str | None] = mapped_column(String(50))  # target/prospective/possible/low
    risk_flags: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    missing_items: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(50), default="new", index=True)  # new/viewed/participating/won/lost
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        CheckConstraint(
            "relevance_score IS NULL OR (relevance_score >= 0 AND relevance_score <= 100)", name="check_relevance_range"
        ),
        CheckConstraint("status IN ('new', 'viewed', 'participating', 'won', 'lost')", name="check_valid_status"),
        CheckConstraint("category IN ('target', 'prospective', 'possible', 'low', NULL)", name="check_valid_category"),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="tenders")

    def __repr__(self) -> str:
        return f"<Tender(id={self.id}, number='{self.tender_number}', score={self.relevance_score})>"


class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # proposal/letter/requirements
    content: Mapped[str] = mapped_column(Text, nullable=False)  # Template with variables
    variables: Mapped[dict] = mapped_column(JSON, default=dict)  # Variable definitions
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("type IN ('proposal', 'letter', 'requirements')", name="check_valid_template_type"),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="templates")

    def __repr__(self) -> str:
        return f"<DocumentTemplate(id={self.id}, name='{self.name}', type='{self.type}')>"


class WonTender(Base):
    """Won tenders imported from external sources for centroid calculation."""

    __tablename__ = "won_tenders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_folder: Mapped[str | None] = mapped_column(String(500))
    text_content: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="won_tenders")

    def __repr__(self) -> str:
        return f"<WonTender(id={self.id}, title='{self.title[:50]}')>"


class WebUser(Base):
    """Web users for API authentication (email + password)."""

    __tablename__ = "web_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    payment_plan: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="web_users")

    def __repr__(self) -> str:
        return f"<WebUser(id={self.id}, email='{self.email}')>"
