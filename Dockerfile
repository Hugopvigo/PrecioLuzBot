FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ bot/

RUN useradd --system appuser && mkdir /data && chown appuser:appuser /data
USER appuser

VOLUME ["/data"]

HEALTHCHECK CMD python -c "import pathlib; pathlib.Path('/data').exists() or exit(1)"

CMD ["python", "-m", "bot.main"]
