FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6-dev libpng-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ bot/

RUN useradd --system appuser && mkdir /data && chown appuser:appuser /data
ENV MPLCONFIGDIR=/data/.matplotlib
ENV MPLBACKEND=Agg
RUN mkdir -p /data/.matplotlib && chown appuser:appuser /data/.matplotlib
USER appuser

VOLUME ["/data"]

HEALTHCHECK CMD python -c "import pathlib; pathlib.Path('/data').exists() or exit(1)"

CMD ["python", "-m", "bot.main"]
