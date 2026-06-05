FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pip install --no-cache-dir pyyaml

ENTRYPOINT ["python", "-m", "qaira_semantic_compiler.orchestrator"]
CMD ["--source", "/repo", "--output", "/output", "--learning", "/learning", "--config", "/config/config.yaml"]
