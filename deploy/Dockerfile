FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY fixtures ./fixtures
COPY config ./config
ENV PATH="/srv/.venv/bin:$PATH" PROVIDER_CONFIG_PATH=/etc/planner/providers.yaml
USER 65534
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
