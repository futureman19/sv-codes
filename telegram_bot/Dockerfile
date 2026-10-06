# Build from REPOSITORY ROOT: docker build -f telegram_bot/Dockerfile .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TELEGRAM_STATE_DB=/data/offset.sqlite3
WORKDIR /app
COPY telegram_bot/requirements.txt /app/telegram_bot/requirements.txt
RUN pip install --no-cache-dir -r telegram_bot/requirements.txt && useradd --uid 10001 --create-home decoder && mkdir /data && chown decoder:decoder /data
COPY poc/svcode /app/poc/svcode
COPY telegram_bot /app/telegram_bot
CMD ["python", "-B", "-m", "telegram_bot.bootstrap"]
