FROM python:3.11-slim

# Встановлюємо системні залежності для Cron та SQLite
RUN apt-get update && apt-get install -y \
    cron \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Створюємо робочу директорію всередині контейнера
WORKDIR /app

# Копіюємо файл залежностей та встановлюємо їх
COPY requirements.txt .
RUN pip install --no-cache-dir python-dotenv && \
    pip install --no-cache-dir -r requirements.txt

# Копіюємо весь код проекту (папку src, конфіги тощо)
COPY . .

# Створюємо папку для бази даних та пустий файл для логів
RUN mkdir -p /app/data && touch /app/YT_project.log

# Налаштовуємо Cron: запускати конвеєр кожні 3 години.
# Зверни увагу: ми викликаємо "python -m src.main", щоб Python правильно бачив усі імпорти всередині папки src!
RUN echo "0 */1 * * * cd /app && /usr/local/bin/python -m src.main >> /app/YT_project.log 2>&1" | crontab -

# Запускаємо службу cron у фоновому режимі, щоб контейнер не закривався
CMD ["cron", "-f"]