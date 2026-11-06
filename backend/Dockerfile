FROM python:3.12-slim

ARG INSTALL_MEDIA=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr tesseract-ocr-tur tesseract-ocr-eng fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-media.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN if [ "$INSTALL_MEDIA" = "true" ]; then \
        pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-media.txt; \
    fi
RUN python -m playwright install --with-deps chromium
COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
