import os
import logging
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv

from src.YouTubeLoader import YoutubeLoader
from src.DatabaseConnector import Database
from src.logging_config import configure_logging

logger = logging.getLogger(__name__)

def run_scraper_pipeline(db_path: str, query_text: str, max_active_limit: int):
    logger.info('Початок циклу легкого скрапера.')
    
    # Підключення до MongoDB (буфер для сирих даних)
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    mongo_client = MongoClient(MONGO_URI)
    mongo_db = mongo_client["youtube_sentiment_db"]
    raw_comments_collection = mongo_db["raw_comments"]
    
    # Ініціалізація підсистем (SQLite для метаданих)
    db = Database(None, db_path=db_path)
    yt = YoutubeLoader()
    
    active_videos = db.get_active_videos()
    if not active_videos:
        logger.info("У базі відсутні активні відео для опрацювання.")
        video_ids = []
        actual_counts = {}
    else:
        video_ids = [v[0] for v in active_videos]
        logger.info(f'Знайдено {len(video_ids)} відео для перевірки.')
        actual_counts = yt.get_actual_comment_counts(video_ids)
    
    processed_this_cycle = []

    for video in active_videos:
        v_id = video[0]
        dpub_raw = video[1]
        db_total_comments = video[2]

        dpub = db._parse_datetime(dpub_raw)
        if not dpub:
            logger.warning(f"Відео {v_id} має некоректну дату публікації — пропускаємо.")
            continue
            
        if dpub.tzinfo is None:
            dpub = dpub.replace(tzinfo=timezone.utc)
        
        age_days = (datetime.now(timezone.utc) - dpub).days
        if age_days > 14:
            logger.info(f"Відео {v_id} старше за 14 днів ({age_days} дн.) — деактивація.")
            db.deactivate_video(v_id)
            continue
        
        yt_count = actual_counts.get(v_id)
        
        if yt_count is None:
            logger.warning(f"Не отримано статистики з API для відео {v_id} — пропускаємо.")
            continue
        
        if age_days > 3 and yt_count <= db_total_comments:
            logger.info(f"Відео {v_id} у буферній зоні ({age_days} дн.) без зростання активності — деактивація.")
            db.deactivate_video(v_id)
            continue

        if yt_count > db_total_comments or age_days <= 3:
            logger.info(f"Відео {v_id} позначено як активне (БД: {db_total_comments}, YT: {yt_count}) — завантаження коментарів.")
            
            last_sync = db.get_last_sync(v_id)
            
            try:
                raw_df = yt.fetch_comment(v_id, last_fetched=last_sync)
            except Exception as e:
                if "commentsDisabled" in str(e):
                    logger.warning(f"Коментарі вимкнені для відео {v_id} — деактивація.")
                    db.deactivate_video(v_id)
                    continue
                raise
            
            if not raw_df.empty:
                logger.info(f"Знайдено {len(raw_df)} нових коментарів для {v_id}. Зберігаємо в MongoDB...")
                
                records = raw_df.to_dict(orient="records")
                for record in records:
                    comment_id = record.get('comment_id') or f"{v_id}_{hash(record.get('text', ''))}"
                    
                    document = {
                        "comment_id": comment_id,
                        "video_id": v_id,
                        "text": record.get('text'),
                        "author": record.get('author'),
                        "published_at": record.get('published_at'),
                        "likes": record.get('likes', 0),
                        "processed": False,  # Прапорець для майбутнього інференсу
                        "fetched_at": datetime.now(timezone.utc)
                    }
                    
                    # Записуємо або оновлюємо за унікальним comment_id
                    raw_comments_collection.update_one(
                        {"comment_id": comment_id},
                        {"$set": document},
                        upsert=True
                    )
                
                # Оновлюємо базові лічильники в SQLite (скільки тепер загалом коментарів на відео)
                new_last_date = raw_df['published_at'].max() if 'published_at' in raw_df.columns else datetime.now(timezone.utc)
                db.update_video_total_count(v_id, yt_count, new_last_date)
                
                processed_this_cycle.append(v_id)
            else:
                logger.info(f"Для відео {v_id} не виявлено нових коментарів.")
                processed_this_cycle.append(v_id)

    if processed_this_cycle:
        db.update_check_timestamps(processed_this_cycle)
    
    # Пошук нових відео, якщо ліміт активних не заповнений
    still_active = db.get_active_videos()
    active_count = len(still_active) if still_active else 0
    
    if active_count < max_active_limit:
        slots_available = max_active_limit - active_count
        logger.info(f"Активних відео менше ліміту ({max_active_limit}) — шукаємо ще {slots_available}.")
        
        discovered_videos = yt.discover_videos_by_keyword(query_text=query_text, max_results=slots_available)
        
        for item in discovered_videos:
            pub_date = db._parse_datetime(item['published_at'])
            db.register_video(
                video_id=item['video_id'],
                channel_id=item['channel_id'],
                title=item['title'],
                channel_name=item['channel_name'],
                date_publication=pub_date,
                is_active=1
            )
            logger.info(f"Зареєстровано нове відео: {item['title']} (ID: {item['video_id']})")
    
    logger.info("--- Цикл легкого скрапера успішно завершено ---")


def main():
    load_dotenv()
    configure_logging()
    
    DB_PATH = os.getenv("DB_PATH", "data/youtube_analytics.db")
    QUERY_TEXT = os.getenv("MONITORING_QUERY", "Зеленський")
    MAX_ACTIVE = int(os.getenv("MAX_ACTIVE_VIDEOS", "15"))
    
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    logger.info("Ініціалізація скрапера завершена.")

    try:
        run_scraper_pipeline(DB_PATH, QUERY_TEXT, MAX_ACTIVE)
    except Exception as e:
        logger.critical(f"Критична помилка скрапера: {e}", exc_info=True)


if __name__ == "__main__":
    main()