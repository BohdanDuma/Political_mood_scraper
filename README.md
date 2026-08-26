# YouTube Comments Sentiment Scraper & Analyzer (POLIT_SCRAPER)

Автоматичний інструмент для збору та аналізу тональності коментарів з YouTube каналів. Проект використовує нейромережі від Hugging Face для глибокого аналізу настроїв користувачів. Переслідує дві головні мети:

1) Автоматизоване створення датасету з оцінками різних моделей — для подальшого аналізу їхньої точності та донавчання.
2) Аналітика психологічного аспекту, політичних настроїв частини українського інфопростору.

Можете ознайомитись на Kaggle: https://www.kaggle.com/datasets/bohdanduma/youtube-politics-sentiment

## 📌 Основні можливості

- **Скрапінг YouTube** — автоматичне збирання коментарів з відео та каналів
- **Аналіз тональності** — визначення позитивних, негативних та нейтральних коментарів за допомогою моделей `cardiffnlp/twitter-xlm-roberta-base-sentiment` та `nlptown/bert-base-multilingual-uncased-sentiment`
- **Розподілена архітектура (v3)** — компоненти розділені за частотою запуску та вагою обчислень і виконуються в різних середовищах (хмара, bare-metal, контейнер)
- **MongoDB як буферний шар** — розв'язує щоденний збір даних і тижневу важку ML-обробку
- **Локальна аналітична база** — збереження результатів інференсу у SQLite
- **Автопублікація датасету на Kaggle** — щотижнева синхронізація через `kagglehub`

## 🛠 Технологічний стек

- Python 3.11+ / 3.13 (Miniconda)
- Hugging Face Transformers (PyTorch)
- MongoDB Atlas (хмарне сховище коментарів)
- Pandas, SQLite
- Docker (легкі компоненти: scraper, publisher)
- GCP Cloud Run Jobs + Cloud Scheduler
- Linux Cron (тижнева оркестрація на хості)
- kagglehub (публікація датасету)

---

## 🆕 Еволюція проєкту: Версія 3.0 (v3) — розподілена архітектура

Проєкт пройшов рефакторинг з монолітного Docker-застосунку (v2, один контейнер `yt_scraper`, одна SQLite-база, ручний або погодинний cron-запуск) у **три незалежні компоненти**, розділені за частотою виконання та вартістю обчислень.

### Чому моноліт довелось розділити

У v2 скрапінг і важкий ML-інференс виконувались в одному циклі й одному контейнері. Це працювало, поки:
- ваги моделей (~1.1 GB кешу у v2) виросли до ансамблю моделей з сумарним відбитком **~30 GB**, що зробило Docker-образ непрактичним для збирання/перенесення;
- потреба збирати коментарі **щодня**, а важкий інференс запускати **раз на тиждень**, змусила розвести ці процеси по різних розкладах;
- зʼявився третій крок — публікація на Kaggle, — який логічно не має нічого спільного зі скрапінгом чи інференсом.

### Нова схема

```
[ ЩОДНЯ ]  GCP Cloud Run Job (Scraper, легкий Docker) ──► MongoDB Atlas (raw_comments)
                                                                  │
                                                                  │  processed: False
                                                                  ▼
[ ЩОТИЖНЯ ]  Analyzer (bare-metal, НЕ в Docker) ──► SQLite (локально)
                    │  exit code 0
                    ▼
             Kaggle Publisher (легкий Docker) ──► Kaggle Dataset
```

| Компонент | Було (v2) | Стало (v3) |
|---|---|---|
| Скрапінг | Частина монолітного циклу, Docker, погодинний cron | Окремий Cloud Run Job, щоденний Cloud Scheduler |
| Сховище коментарів | Одразу SQLite | MongoDB Atlas (staging) → SQLite (аналітика) |
| ML-інференс | В тому ж Docker-контейнері | Bare-metal процес на хості (без Docker) |
| Публікація датасету | Відсутня / ручна | Окремий легкий Docker-контейнер, автоматизована |
| Оркестрація | Один `docker compose exec` | bash-скрипт з перевіркою exit code між кроками |

### 🔥 Ключові архітектурні рішення v3

* **Розділення за вартістю обчислень, а не лише за функцією.** Легкі, часті задачі (скрапінг, публікація) — у контейнерах, де переносимість і швидкий build мають цінність. Важкий інференс — напряму на хості, оскільки контейнеризація 30 GB моделей не дає функціональної переваги для процесу, що завжди виконується на одній відомій машині.
* **MongoDB як proizводчик/споживач різної частоти.** Scraper пише в `raw_comments` з прапорцем `processed: False`; Analyzer вичитує лише необроблені записи й позначає їх `True` після інференсу — класичний staging-патерн, що розв'язує щоденний і щотижневий цикли.
* **Dual-Model Pipeline** (успадковано з v2, тепер працює над Mongo-даними): паралельна оцінка `cardiffnlp` (3-класова) і `nlptown` (5-зіркова) для порівняння точності моделей.
* **Явний контроль потоку через exit code**, а не оркестратор (Airflow тощо) — свідомий вибір, пропорційний масштабу пайплайну (два послідовні кроки без розгалужень). Kaggle-публікація запускається лише якщо Analyzer завершився з `exit code 0`.
* **Ідемпотентність на кожному етапі** — `upsert` за `comment_id` у Mongo, full-refresh експорт у Kaggle. Повторний запуск будь-якого кроку безпечний.

---

## 🚀 Встановлення та запуск (v3)

Кожен компонент розгортається і запускається окремо.

### Компонент 1: Scraper — GCP Cloud Run Job

1. **Зберіть і задеплойте образ**

   ```bash
   gcloud builds submit --tag europe-west1-docker.pkg.dev/PROJECT_ID/repo/youtube-scraper:latest
   
   gcloud run jobs create youtube-scraper-sandbox \
     --image=europe-west1-docker.pkg.dev/PROJECT_ID/repo/youtube-scraper:latest \
     --region=europe-west1 \
     --set-env-vars=MONGO_URL=...,MONITORING_QUERY=...,MAX_ACTIVE_VIDEOS=15
   ```

2. **Ручний запуск (для тесту)**

   ```bash
   gcloud run jobs execute youtube-scraper-sandbox --region=europe-west1 --project=youtubepolitscarper
   ```

3. **Автоматизація через Cloud Scheduler (щодня)**

   ```bash
   gcloud scheduler jobs create http scraper-daily-trigger \
     --location=europe-west1 \
     --schedule="0 6 * * *" \
     --uri="https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/youtube-scraper-sandbox:run" \
     --http-method=POST \
     --oauth-service-account-email=SCHEDULER_SA@PROJECT_ID.iam.gserviceaccount.com
   ```

### Компонент 2: Analyzer — bare-metal (Miniconda + Cron)

Не контейнеризується свідомо (див. розділ архітектурних рішень вище).

1. **Встановіть залежності в conda-середовищі**

   ```bash
   conda create -n polit-analyzer python=3.11
   conda activate polit-analyzer
   pip install -r requirements.txt
   ```

2. **Налаштуйте `.env`**

   ```
   MONGO_URL=mongodb+srv://...
   DB_PATH=data/youtube_analytics.db
   ```

3. **Тестовий запуск**

   ```bash
   PYTHONPATH=. python src/heavy_worker.py
   ```

4. **Автоматизація через Cron (щотижня)** — виконується разом з Kaggle Publisher одним bash-скриптом, див. розділ нижче.

### Компонент 3: Kaggle Publisher — легкий Docker

1. **Налаштуйте `.env`**

   ```bash
   cp .env.example .env
   ```
   ```
   DB_PATH=/app/data/youtube_analytics.db
   EXPORT_DIR=/app/export
   DATASET_HANDLE=bohdanduma/youtube-politics-sentiment
   GOLD_STANDARD_PATH=/app/data/manual_annotation_2026-07-14.csv
   ```

2. **Зберіть образ**

   ```bash
   docker build -t kaggle-uploader:latest -f Dockerfile.kaggle .
   ```

3. **Ручний запуск**

   ```bash
   docker run --rm \
     -v ~/.kaggle/kaggle.json:/root/.kaggle/kaggle.json:ro \
     -v $(pwd)/data:/app/data \
     --env-file .env \
     kaggle-uploader:latest
   ```

### Оркестрація: тижневий пайплайн (Analyzer → Kaggle Publisher)

Обидва кроки запускаються послідовно одним bash-скриптом з явною перевіркою exit code — публікація на Kaggle виконується **лише** при успішному завершенні Analyzer.

`run_weekly_pipeline.sh`:

```bash
#!/bin/bash
set -uo pipefail

PROJECT_DIR="/home/USER/Political_mood_scraper"
PYTHON_BIN="/home/USER/miniconda3/envs/polit-analyzer/bin/python"

cd "$PROJECT_DIR"
PYTHONPATH=. "$PYTHON_BIN" src/heavy_worker.py
ANALYZER_EXIT=$?

if [ $ANALYZER_EXIT -ne 0 ]; then
    echo "Analyzer failed (exit $ANALYZER_EXIT). Kaggle publish skipped."
    exit 1
fi

docker run --rm \
    -v ~/.kaggle/kaggle.json:/root/.kaggle/kaggle.json:ro \
    -v "$PROJECT_DIR/data:/app/data" \
    --env-file "$PROJECT_DIR/.env" \
    kaggle-uploader:latest
```

Cron (щопонеділка о 3:00):

```bash
crontab -e
```
```plaintext
0 3 * * 1 /home/USER/Political_mood_scraper/run_weekly_pipeline.sh >> /home/USER/Political_mood_scraper/logs/cron.log 2>&1
```

---

## ⚠️ Важливо про GPU

Analyzer виконується на bare-metal саме для повного доступу до GPU без прошарку віртуалізації Docker. Для CUDA-прискорення на хості:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

Scraper і Kaggle Publisher не потребують GPU — залишаються легкими CPU-only образами.

---

## ⚙️ Конфігурація

- **`.env`** — секрети та API-ключі для кожного компонента окремо (не в репозиторії)
- **`~/.kaggle/kaggle.json`** — credentials для kagglehub, монтується в Kaggle Publisher як read-only volume
- **`cache/huggingface`** — локальний кеш ваг моделей на хості Analyzer (ігнорується Git)
- **`data/`** — директорія з SQLite базою (Analyzer ↔ Kaggle Publisher)
- **MongoDB Atlas** — конфігурується через `MONGO_URL`, спільна для Scraper і Analyzer

## 📂 Структура проекту

```
Political_mood_scraper/
├── cache/                       # Кеш ваг моделей (Analyzer, bare-metal)
│   └── huggingface/hub/
├── data/                        # SQLite база, export CSV, gold standard
├── src/
│   ├── scraper/
│   │   └── main.py              # Точка входу Scraper (Cloud Run Job)
│   ├── analyzer/
│   │   └── heavy_worker.py      # Точка входу Analyzer (bare-metal)
│   ├── kaggle_publisher/
│   │   └── upload.py            # Точка входу Kaggle Publisher (Docker)
│   ├── DataTransform.py         # Sentiment-обробка (спільна для v2/v3)
│   ├── DatabaseConnector.py     # Робота з SQLite
│   ├── ModelManager.py          # Factory для NLP-моделей
│   └── YouTubeLoader.py         # Логіка YouTube API
├── run_weekly_pipeline.sh       # Оркестрація Analyzer → Kaggle Publisher
├── Dockerfile.scraper
├── Dockerfile.kaggle
├── .env                         # Конфігурація (локально, не в репо)
├── pyproject.toml
└── requirements.txt
```

## 💾 Збережені дані

- **`cache/huggingface`** — кеш моделей на хості Analyzer (~30 GB для повного ансамблю)
- **`data/youtube_analytics.db`** — аналітична SQLite-база (video_info, raw_comments, model_info, global_stats)
- **MongoDB `raw_comments`** — сирі коментарі зі статусом обробки (staging layer між Scraper і Analyzer)

## 🤝 Внесок

Ми вітаємо pull request-и! Для значних змін будь ласка відкрийте issue з описом пропозицій.

## 📄 Ліцензія

MIT License — див. файл `LICENSE` для деталей.

---

**Потребуєте допомоги?** Відкрийте issue або зв'яжіться з командою розробки.
