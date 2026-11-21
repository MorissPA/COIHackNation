# Kreator e-Usług COI

Usługa REST analizuje blankiety PDF, DOC, DOCX, ODS, XLSX, JPG, JPEG i PNG oraz zwraca strukturę formularza zgodną ze schematem JSON aplikacji docelowej. Dane są przetwarzane wyłącznie w pamięci/`/tmp` i nie są trwałe.

## REST API

- `GET /health` — sprawdzenie stanu usługi.
- `GET /` — prosty frontend do wgrywania i edycji rozpoznanych pól.
- `POST /api/v1/forms/analyze` — analiza jednego pliku. Pole żądania `multipart/form-data` nazywa się `file`.

```bash
curl -F "file=@wniosek.pdf" http://localhost:8080/api/v1/forms/analyze
```

Odpowiedź zawiera `serviceMetadata`, `dictionaries` i strony z polami. Usługa akceptuje podpisy MIME dopasowane do rozszerzenia. Nazwa pliku może mieć maksymalnie 250 znaków i nie może zawierać `; : > < / \\ | ' * % $` ani znaków sterujących. Błędny typ zwraca `415`, błędna nazwa `400`, a przekroczony rozmiar `413`.

## Konfiguracja

- `MAX_UPLOAD_SIZE` — maksymalny rozmiar pliku w bajtach; domyślnie `15728640` (15 MB).
- `FRONTEND_DIR` — opcjonalna ścieżka do katalogu frontend; domyślnie katalog `frontend` w repozytorium.

Usługa nie wymaga obecnie JWT ani połączenia z zewnętrznym API. Jeżeli uwierzytelnianie zostanie dodane, parametry powinny być przekazywane wyłącznie przez zmienne środowiskowe w czasie uruchomienia.

## Uruchomienie lokalnie

Wymagane: Python 3.14+ oraz systemowe `tesseract` z polskim językiem OCR.

```bash
python -m pip install -r requirements.txt
MAX_UPLOAD_SIZE=15728640 uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Docker

```bash
docker build -t coi-form-generator .
docker run --rm -p 8080:8080 -e MAX_UPLOAD_SIZE=15728640 coi-form-generator
```

Lub Docker Compose:

```bash
docker compose up --build
```

Aplikacja będzie dostępna pod `http://localhost:8080`.