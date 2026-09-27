FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir unidiff pytest boto3
WORKDIR /app
COPY annotate.py pack.py entrypoint.py ./
COPY core/ ./core/
COPY tests/ ./tests/
COPY REVIEW_TEMPLATE.md GUIDELINES_V2.md ./
ENV OUTPUT_DIR=/work
ENV PYTHONDONTWRITEBYTECODE=1
RUN mkdir -p /work
ENTRYPOINT ["python", "-u", "/app/entrypoint.py"]
