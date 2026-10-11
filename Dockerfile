FROM python:3.10-slim

LABEL maintainer="IIT Pune — Code to Connect 2026"
LABEL description="S&P 100 NLP Risk Engine Backend"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch>=2.0.0 --index-url ${TORCH_INDEX} && \
    pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY data/ ./data/

RUN mkdir -p \
    src/output/rebalancing_outputs \
    src/output/risk_engine_outputs \
    src/output/stress_test_outputs \
    data/live_mode_fetched

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/ping')" || exit 1

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
