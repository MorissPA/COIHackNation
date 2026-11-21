FROM python:3.14-alpine3.22

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

RUN apk add --no-cache tesseract-ocr tesseract-ocr-data-pol tesseract-ocr-data-eng

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY frontend ./frontend

USER appuser
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
