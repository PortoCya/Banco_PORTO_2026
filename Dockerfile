# Imagem única para API, worker de IA e migrations (o comando muda no compose).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini main.py seed_db.py check_db.py ./
COPY alembic ./alembic
COPY app ./app

# Não roda como root
RUN useradd --system --uid 10001 nps
USER nps

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
