FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir unidiff

WORKDIR /app
COPY annotate.py pack.py entrypoint.py ./
RUN mkdir -p /work

ENTRYPOINT ["python", "/app/entrypoint.py"]