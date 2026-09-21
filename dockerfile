FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# gcc и libpq-dev нужны только для сборки колёс, в готовом образе они
# не нужны — удаляем их в том же слое, иначе останутся в истории образа.
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc libpq-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Рабочие каталоги создаём заранее и отдаём приложению: контейнер
# работает не от root, писать в /app он иначе не сможет.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p cache downloads outputs won_tenders \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "web_main:app", "--host", "0.0.0.0", "--port", "8000"]
