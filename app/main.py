from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any
import io
import os
import re
import tempfile
import zipfile

app = FastAPI(title="Kreator e-Usług COI", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(15 * 1024 * 1024)))
FORBIDDEN_FILENAME_CHARS = set(';:><\\/|\'*%$')
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "ods", "xlsx", "jpg", "jpeg", "png"}


class Field(BaseModel):
    id: str
    label: str
    type: str = "text"
    required: bool = True
    validation: str | None = None
    dictionaryRef: str | None = None
    visibilityCondition: dict[str, Any] | None = None


class Page(BaseModel):
    pageNumber: int
    pageId: str
    title: str
    fields: list[Field]


class Result(BaseModel):
    schemaVersion: str = "COI-EUSLUGA-2026.1"
    serviceMetadata: dict[str, Any]
    dictionaries: list[dict[str, Any]]
    pages: list[Page]


def validate_name(name: str) -> None:
    if len(name) > 250:
        raise HTTPException(status_code=400, detail="Nazwa pliku przekracza 250 znaków.")
    if any(char in FORBIDDEN_FILENAME_CHARS for char in name):
        raise HTTPException(status_code=400, detail="Nazwa pliku zawiera niedozwolony znak.")


def detect_format(filename: str, data: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Nieobsługiwany typ pliku: .{ext}")

    signatures = {
        "pdf": data.startswith(b"%PDF-"),
        "doc": data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
        "docx": ext == "docx" and data.startswith(b"PK") and zipfile.is_zipfile(io.BytesIO(data)),
        "ods": ext == "ods" and data.startswith(b"PK") and zipfile.is_zipfile(io.BytesIO(data)),
        "xlsx": ext == "xlsx" and data.startswith(b"PK") and zipfile.is_zipfile(io.BytesIO(data)),
        "jpg": data.startswith(b"\xff\xd8\xff"),
        "jpeg": data.startswith(b"\xff\xd8\xff"),
        "png": data.startswith(b"\x89PNG\r\n\x1a\n"),
    }
    if not signatures.get(ext, False):
        raise HTTPException(status_code=415, detail="MIME: zawartość pliku nie odpowiada rozszerzeniu.")
    return ext


def normalize_label(raw: str) -> str:
    raw = re.sub(r"\s+", " ", raw).strip(" :-._")
    return raw[:180] if raw else "Pole formularza"


def extract_text(data: bytes, fmt: str) -> str:
    if fmt == "pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return ""
    if fmt == "docx":
        try:
            from docx import Document
            document = Document(io.BytesIO(data))
            return "\n".join(p.text for p in document.paragraphs)
        except Exception:
            return ""
    if fmt == "xlsx":
        try:
            from openpyxl import load_workbook
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            return "\n".join(str(cell.value) for sheet in workbook for row in sheet.iter_rows() for cell in row if cell.value is not None)
        except Exception:
            return ""
    if fmt == "ods":
        try:
            from odf.opendocument import load
            from odf.table import Table, TableRow, TableCell
            from odf.text import P
            document = load(io.BytesIO(data))
            parts: list[str] = []
            for paragraph in document.getElementsByType(P):
                parts.append("".join(str(child) for child in paragraph.childNodes))
            return "\n".join(parts)
        except Exception:
            return ""
    if fmt in {"jpg", "jpeg", "png"}:
        try:
            import pytesseract
            from PIL import Image
            with tempfile.NamedTemporaryFile(suffix=f".{fmt}") as temp:
                temp.write(data)
                temp.flush()
                return pytesseract.image_to_string(Image.open(temp.name), lang="pol+eng")
        except Exception:
            return ""
    if fmt == "doc":
        return ""
    return ""


def infer_field(label: str) -> tuple[str, str | None, str | None]:
    lower = label.lower()
    if "pesel" in lower:
        return "pesel", "PESEL", None
    if "kod poczt" in lower:
        return "text", "POSTAL_CODE", None
    if "telefon" in lower or "numer telefonu" in lower:
        return "text", "PHONE_PL", None
    if "email" in lower or "e-mail" in lower:
        return "text", "EMAIL", None
    if "wojew" in lower:
        return "select", None, "TERYT_WOJEWODZTWA"
    if "miejscow" in lower or "miasto" in lower:
        return "select", None, "TERYT_MIEJSCOWOSCI"
    if "data" in lower:
        return "date", None, None
    return "text", None, None


def heuristic_extract(text: str, filename: str, fmt: str) -> Result:
    candidates: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"[_]{3,}|[.]{3,}|\[.*?\]", "", line)
        line = line.strip(" -*•0123456789.")
        if 3 <= len(line) <= 180:
            candidates.append(normalize_label(line))

    if not candidates:
        candidates = ["Numer PESEL", "Imię", "Nazwisko", "Adres korespondencyjny"]

    unique: list[str] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    candidates = unique[:30]

    fields: list[Field] = []
    dictionaries: list[dict[str, Any]] = []
    seen_dictionaries: set[str] = set()

    for index, label in enumerate(candidates, start=1):
        field_type, validation, dictionary = infer_field(label)
        fields.append(Field(id=f"pole_{index}", label=label, type=field_type, required=True,
                            validation=validation, dictionaryRef=dictionary))
        if dictionary and dictionary not in seen_dictionaries:
            seen_dictionaries.add(dictionary)
            dictionaries.append({"dictionaryCode": dictionary, "status": "COI_VERIFIED", "values": []})

    return Result(
        serviceMetadata={
            "serviceCode": "USL-GENERATED",
            "title": normalize_label(filename.rsplit(".", 1)[0].replace("_", " ")),
            "sourceFileName": filename,
            "sourceFormat": fmt,
        },
        dictionaries=dictionaries,
        pages=[Page(pageNumber=1, pageId="strona-1", title="Strona 1: Dane wnioskodawcy", fields=fields)],
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/forms/analyze", response_model=Result)
async def analyze_form(file: UploadFile = File(...)) -> Result:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Brak nazwy pliku.")
    validate_name(file.filename)

    data = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Plik przekracza skonfigurowany maksymalny rozmiar.")

    fmt = detect_format(file.filename, data)
    text = extract_text(data, fmt)
    return heuristic_extract(text, file.filename, fmt)


@app.get("/")
def frontend() -> FileResponse:
    return FileResponse("/app/frontend/index.html")


static_dir = "/app/frontend"
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
