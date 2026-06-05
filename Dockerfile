FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir \
    pyyaml \
    tree-sitter \
    tree-sitter-javascript \
    tree-sitter-typescript \
    && chmod +x /app/run_qaira_semantic_compiler.sh

ENV QAIRA_SOURCE=/repo
ENV QAIRA_OUTPUT=/output
ENV QAIRA_CONFIG=/config/config.yaml
ENV QAIRA_LEARNING=/learning

ENTRYPOINT ["/app/run_qaira_semantic_compiler.sh"]
CMD ["/repo", "/output", "/config/config.yaml", "", "/learning"]
