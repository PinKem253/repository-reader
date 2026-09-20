FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml .
COPY uv.lock .
RUN pip install uv
RUN uv sync --frozen --no-install-project
COPY src/ ./src/
COPY README.md .
RUN uv sync --frozen
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "repository_reader.app:app", "--host", "0.0.0.0"]
