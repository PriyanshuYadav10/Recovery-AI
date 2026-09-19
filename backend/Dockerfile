# Recovery AI brain - FastAPI + the lead scoring model.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

# Dependencies first so the layer caches across code changes.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Config and data live outside backend/ and are read at runtime.
COPY config /app/config
COPY data /app/data
COPY backend /app/backend

WORKDIR /app/backend

# Train the model at build time if no artifact was committed, so the image is
# never served with the heuristic fallback by accident.
RUN python -c "import pathlib,sys; sys.exit(0 if pathlib.Path('app/ml/artifacts/lead_scorer.joblib').exists() else 1)" \
    || (python app/ml/dataset.py && python app/ml/train.py)

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health').read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
