import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

# Додаємо кореневу директорію проєкту до sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

try:
    from src.DataTransform import DataTransformer
    from src.DatabaseConnector import Database
    from src.ModelManager import ModelFactory
    from src.logging_config import configure_logging
    import logging
except ModuleNotFoundError:
    from DataTransform import DataTransformer
    from DatabaseConnector import Database
    from ModelManager import ModelFactory
    from logging_config import configure_logging
    import logging

logger = logging.getLogger(__name__)

def run_heavy_inference_pipeline(db_path: str, model_ids: list = None):
    logger.info('Початок циклу важкої обробки коментарів (ML Inference).')
    
    # Ініціалізація моделей
    if model_ids is None:
        model_ids = [
            'cardiffnlp/twitter-xlm-roberta-base-sentiment',
            'nlptown/bert-base-multilingual-uncased-sentiment'
        ]
    
    models = {}
    for mid in model_ids:
        try:
            models[mid] = ModelFactory.get_model(mid)
        except Exception as e:
            logger.error('Не вдалося завантажити модель %s: %s', mid, e)
            
    if not models:
        logger.critical('Не завантажено жодної моделі — припиняю виконання циклу')
        return
        
    logger.info(f"Завантажено {len(models)} моделей для оцінки: {list(models.keys())}")
    
    # Підключення до аналітичної SQLite БД та MongoDB
    db = Database(None, db_path=db_path)
    
    MONGO_URI = os.getenv("MONGO_URL", "mongodb+srv://musclesoulb_db_user:llathe23@cluster0.hwerv3r.mongodb.net/?appName=Cluster0")
    mongo_client = MongoClient(MONGO_URI)
    mongo_db = mongo_client["youtube_sentiment_db"]
    raw_comments_col = mongo_db["raw_comments"]
    videos_col = mongo_db["videos"]
    
    # 1. Backfill заголовків у SQLite (оригінальна логіка)
    try:
        for model_name, model in models.items():
            logger.info(f"Запуск backfill заголовків для моделі: {model_name}")
            transformer_title = DataTransformer(model=model)
            db.backfill_title_sentiments(transformer_title)
    except Exception as e:
        logger.exception('Помилка під час заповнення пропущених міток настрою для заголовків: %s', e)

    # 2. Отримання коментарів з MongoDB, що ще не пройшли ML-обробку
    unprocessed_docs = list(raw_comments_col.find({"processed": False}))
    
    if not unprocessed_docs:
        logger.info("У MongoDB відсутні нові необроблені коментарі (processed == False).")
    else:
        logger.info(f"Знайдено {len(unprocessed_docs)} нових коментарів. Групуємо за video_id...")
        
        # Групуємо коментарі за відео
        comments_by_video = {}
        for doc in unprocessed_docs:
            v_id = doc.get("video_id")
            if v_id not in comments_by_video:
                comments_by_video[v_id] = []
            comments_by_video[v_id].append(doc)

        for v_id, docs in comments_by_video.items():
            logger.info(f"Початок аналізу {len(docs)} коментарів для відео: {v_id}")

            # Реєструємо/перевіряємо наявність відео в SQLite
            video_doc = videos_col.find_one({"video_id": v_id})
            if video_doc:
                db.register_video(
                    video_id=video_doc['video_id'],
                    channel_id=video_doc.get('channel_id', ''),
                    title=video_doc.get('title', ''),
                    channel_name=video_doc.get('channel_name', ''),
                    date_publication=video_doc.get('date_publication'),
                    is_active=video_doc.get('is_active', 1)
                )
                yt_count = video_doc.get("total_comments", len(docs))
            else:
                yt_count = len(docs)

            # Формуємо DataFrame з коментарів для DataTransformer
            raw_df = pd.DataFrame(docs)
            
            # Переконуємось у наявності необхідних полів
            for col in ['comment_id', 'text', 'author', 'published_at', 'likes']:
                if col not in raw_df.columns:
                    raw_df[col] = None

            comment_ids_processed = [doc["comment_id"] for doc in docs if "comment_id" in doc]

            # 3. ОБРОБКА КОЖНОЮ МОДЕЛЛЮ (оригінальний блок DataTransformer)
            for model_name, sentiment_model in models.items():
                logger.info(f"Обробка коментарів для {v_id} моделлю {model_name}")
                transformer = DataTransformer(raw_df.copy(), model=sentiment_model)
                
                try:
                    mood_column = 'mood' if 'mood' in transformer.df.columns else 'sentiment_label'
                    sentiment_labels = transformer.df[mood_column].tolist()
                    transformer.df = transformer.df.copy()
                    transformer.df['video_id'] = v_id
                    
                    # Збереження розмічених коментарів у SQLite
                    db.save_raw_comments(transformer.df, sentiment_labels, model_name)
                except Exception as e:
                    logger.exception('Помилка масового збереження коментарів для %s моделлю %s: %s', v_id, model_name, e)
                
                stats = transformer.get_aggregated_stats()
                new_last_date = transformer.get_latest_comment_date()
                stats['new_total_comments'] = yt_count
                
                # Оновлення агрегованої статистики відео у SQLite
                db.update_video_stats(v_id, model_name, stats, new_last_date)
                logger.info(f"Статистика для {v_id} (модель: {model_name}) оновлена")

            # 4. Позначаємо ці коментарі як оброблені в MongoDB
            if comment_ids_processed:
                raw_comments_col.update_many(
                    {"comment_id": {"$in": comment_ids_processed}},
                    {"$set": {"processed": True}}
                )
                logger.info(f"Успішно позначено {len(comment_ids_processed)} коментарів як processed=True у MongoDB.")

    # 5. Глобальні метрики настрою (оригінальна логіка)
    logger.info("Запис глобальних метрик настрою для всіх моделей...")
    try:
        for model_id in model_ids:
            p, n, nu, l, v, c = db.global_stats_sentiment(model_id)
            logger.info(f"[{model_id}] Позитив: {p}, Негатив: {n}, Нейтральні: {nu}, Лайки: {l}, Коментарів: {c}, Відео: {v}")
    except Exception as e:
        logger.error(f"Не вдалося записати глобальні метрики настрою: {e}")        
    
    mongo_client.close()
    logger.info("--- Цикл важкої обробки успішно завершено ---")


def main():
    load_dotenv()
    configure_logging()
    
    DB_PATH = os.getenv("DB_PATH", "data/youtube_analytics.db")
    
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    logger.info("Ініціалізація heavy worker завершена — запуск ML конвеєру.")

    try:
        run_heavy_inference_pipeline(DB_PATH)
    except Exception as e:
        try:
            setattr(logger, "colors", False)
        except Exception:
            pass
        logger.critical(f"Критична помилка конвеєру обробки: {e}", exc_info=True)
    
    logger.info("Heavy worker завершив роботу.")


if __name__ == "__main__":
    main()