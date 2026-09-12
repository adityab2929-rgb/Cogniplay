# ===========================================================================
# CogniPlay AI Service
# ===========================================================================
# Python 3.11 here; the source also runs unchanged on the 3.9 used for local
# development (typing.Optional / typing.List only, no PEP 604 unions).
# ===========================================================================
FROM python:3.11-slim

# Keep the image lean and the logs live:
#   PYTHONDONTWRITEBYTECODE -- no .pyc clutter in the layer
#   PYTHONUNBUFFERED        -- uvicorn logs stream to `docker logs` immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Requirements first, so editing source does not invalidate the pip layer.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

# Verify the optional-dependency status of a running container.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
