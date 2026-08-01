# Migration Copilot — self-contained image (API + built React UI).
#
#   docker build -t migration-copilot .
#   docker run -p 8321:8321 migration-copilot
#
# Ollama for expression translation runs on the host or a sidecar; point the
# Settings page at it (e.g. OLLAMA_HOST=host.docker.internal:11434).

FROM node:20-slim AS ui
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
# editable install keeps repo-relative paths (rules/, docs/, samples/) working
RUN pip install --no-cache-dir -e ".[api,schema,llm]"
COPY rules/ rules/
COPY docs/ docs/
# the demo pickers' curated samples (not the 380 MB research corpus)
COPY samples/m_load_sales.xml samples/m_load_sales.xml
COPY samples/informatica/ samples/informatica/
COPY samples/talend_demo/ samples/talend_demo/
COPY samples/crystal/demo/ samples/crystal/demo/
COPY samples/xactions/corpus/steel-wheels-reports/ samples/xactions/corpus/steel-wheels-reports/
COPY CHANGELOG.md VERSION.md ./
COPY --from=ui /app/frontend/dist frontend/dist

# project store, estate sources and deliverable packs live here - mount
# it to keep an engagement across container restarts
ENV PENTAHO_MIGRATION_CONFIG_DIR=/data
VOLUME /data

EXPOSE 8321
ENV PYTHONUNBUFFERED=1
# single worker BY DESIGN: background jobs (gate, review, sweeps, packs)
# live in process memory - more workers would break job polling
CMD ["uvicorn", "pentaho_migration.api.main:app", "--host", "0.0.0.0", "--port", "8321"]
