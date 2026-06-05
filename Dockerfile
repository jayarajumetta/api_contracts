FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir \
    pyyaml \
    tree-sitter \
    tree-sitter-javascript \
    tree-sitter-typescript

ENTRYPOINT ["python", "-m", "qaira_semantic_compiler.orchestrator_v63"]
CMD ["--source", "/repo", "--output", "/output", "--learning", "/learning", "--config", "/config/config.yaml"]
