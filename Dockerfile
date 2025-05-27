FROM python:3.11-slim

# Устанавливаем базовые зависимости
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml poetry.lock* /app/
RUN pip install poetry && poetry install --no-root

# Добавляем необходимые библиотеки
RUN poetry install --no-root

COPY . .

CMD ["poetry", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]