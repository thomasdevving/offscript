# OFFSCRIPT API - FastAPI + Microsoft Agent Framework (Azure Container Apps target)
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY apps/api/requirements.lock /srv/requirements.lock
RUN pip install -r /srv/requirements.lock
COPY apps/api/app /srv/app
COPY scenarios /srv/scenarios
ENV SCENARIOS_DIR=/srv/scenarios DATA_DIR=/srv/data ENVIRONMENT=azure
RUN useradd --create-home --uid 10001 offscript && mkdir -p /srv/data && chown -R offscript /srv/data
USER offscript
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
