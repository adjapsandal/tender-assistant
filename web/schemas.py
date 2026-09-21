from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SKUResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    keywords: str
    exceptions: str | None
    is_active: bool


class SKUCreateRequest(BaseModel):
    name: str
    keywords: str
    description: str | None = None
    exceptions: str | None = None

    model_config = ConfigDict(extra="forbid")


class SKUUpdateRequest(BaseModel):
    name: str | None = None
    keywords: str | None = None
    description: str | None = None
    exceptions: str | None = None
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid")


class CategoryInfo(BaseModel):
    label: str
    color: str


class TenderBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tender_number: str
    title: str
    customer: str | None
    price: str | None
    deadline: str | None
    url: str | None
    relevance_score: float | None
    category: str | None


class TenderDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tender_number: str
    title: str
    customer: str | None
    price: str | None
    deadline: str | None
    description: str | None
    requirements: str | None
    url: str | None
    relevance_score: float | None
    category: str | None
    category_info: CategoryInfo | None
    risk_flags: list[str]
    missing_items: list[str]
    status: str
    created_at: datetime
    generated_files: list[str]


class SearchRequest(BaseModel):
    region: str = ""
    industry: str = ""
    keyword: str = ""
    sku_id: int = 0


class SearchResponse(BaseModel):
    tenders: list[TenderBrief]
    count: int


class TendersListResponse(BaseModel):
    tenders: list[TenderBrief]
    count: int
    page: int
    per_page: int
    total_pages: int


class TenderFileResponse(BaseModel):
    id: str
    title: str
    url: str
    extension: str


class TenderFilesListResponse(BaseModel):
    files: list[TenderFileResponse]
    count: int


class GenerateResponse(BaseModel):
    status: str
    files: list[str]


class WonTenderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_folder: str | None
    has_embedding: bool
    created_at: datetime


class WonTendersListResponse(BaseModel):
    won_tenders: list[WonTenderResponse]
    count: int
    has_centroid: bool


class ImportRequest(BaseModel):
    folder_path: str


class ImportResponse(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


class MessageResponse(BaseModel):
    status: str
    message: str


# ── Auth schemas ──


class UserRegisterRequest(BaseModel):
    email: str
    password: str
    company_name: str

    model_config = ConfigDict(extra="forbid")


class UserLoginRequest(BaseModel):
    email: str
    password: str

    model_config = ConfigDict(extra="forbid")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    company_id: int
    is_active: bool
    payment_plan: str | None
    created_at: datetime


# ── Company schemas ──


class CompanyUpdateRequest(BaseModel):
    name: str | None = None
    full_name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    address: str | None = None
    phone: str | None = None
    director: str | None = None

    model_config = ConfigDict(extra="forbid")


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    full_name: str | None
    inn: str | None
    kpp: str | None
    ogrn: str | None
    address: str | None
    phone: str | None
    director: str | None
    created_at: datetime


class CompanyDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    is_default: bool
    created_at: datetime


class CompanyDocumentsListResponse(BaseModel):
    documents: list[CompanyDocumentResponse]
    count: int
