# Build from repository root: docker build -f mint/Dockerfile .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY mint/requirements.txt /app/mint/requirements.txt
RUN pip install --no-cache-dir -r /app/mint/requirements.txt
# Selective copies: never include local environments, keys, databases or artifacts.
COPY poc/svcode/ /app/poc/svcode/
COPY poc/make_genesis_001.py /app/poc/make_genesis_001.py
COPY mint/server.py mint/txbuilder.py /app/mint/
ENV DB_PATH=/data/mint.db
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "mint.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log"]
