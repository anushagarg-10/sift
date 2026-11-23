FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so they are cached between code changes.
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    python -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); \
print('\n'.join(d['project']['dependencies'] + d['project']['optional-dependencies']['dev']))" \
    > /tmp/requirements.txt && \
    pip install -r /tmp/requirements.txt

COPY app ./app
COPY evals ./evals
COPY sample_data ./sample_data
COPY tests ./tests

RUN useradd --create-home --uid 1000 sift && chown -R sift /app
USER sift

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
