FROM python:3.12.3-slim

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_DEFAULT_TIMEOUT=120
ARG UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV UV_PROJECT_ENVIRONMENT="/usr/local/"
ENV UV_COMPILE_BYTECODE=1
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV PIP_DEFAULT_TIMEOUT=${PIP_DEFAULT_TIMEOUT}
ENV UV_INDEX_URL=${UV_INDEX_URL}

COPY pyproject.toml .
COPY uv.lock .
RUN pip install --no-cache-dir uv

# Install only the dependencies needed for the client application
# --frozen: Use exact versions from the lock file
# --only-group client: Only install dependencies marked as part of the "client" group in pyproject.toml
RUN uv sync --frozen --only-group client

COPY src/client/ ./client/
COPY src/coursepilot/ ./coursepilot/
COPY src/schema/ ./schema/
COPY src/voice/ ./voice/
COPY src/streamlit_app.py .

CMD ["streamlit", "run", "streamlit_app.py"]
