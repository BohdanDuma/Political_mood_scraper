import os
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv
sys.path.append(str(Path(__file__).resolve().parent.parent))
from YouTubeLoader import YoutubeLoader
from logging_config import configure_logging

logger = logging.getLogger(__name__)
load_dotenv()

def run_scraper_pipeline(query_text: str, max_active_limit: int):
    logger.info('Початок циклу легкого скрапера (MongoDB).')
    
    # Підключення до MongoDB Atlas / локального MongoDB
    MONGO_URI = os.getenv("MONGO_URL")
    if not MONGO_URI:
        raise ValueError("CRITICAL ERROR: Змінна оточення MONGO_URL не встановлена!")
    mongo_client = MongoClient(MONGO_URI)
    mongo_db = mongo_client["youtube_sentiment_db"]
    raw_comments_collection = mongo_db["raw_comments"]
    videos_collection = mongo_db["videos"]
    
    yt = YoutubeLoader()
    
    # Отримуємо активні відео з MongoDB
    active_videos = list(videos_collection.find({"is_active": 1}))
    
    if not active_videos:
        logger.info("У базі відсутні активні відео для опрацювання.")
        video_ids = []
        actual_counts = {}
    else:
        video_ids = [v["video_id"] for v in active_videos]
        logger.info(f'Знайдено {len(video_ids)} відео для перевірки.')
        actual_counts = yt.get_actual_comment_counts(video_ids)
    
    now_utc = datetime.now(timezone.utc)

    for video in active_videos:
        v_id = video["video_id"]
        dpub = video.get("date_publication")
        db_total_comments = video.get("total_comments", 0)

        if not dpub:
            logger.warning(f"Відео {v_id} має некоректну дату публікації — пропускаємо.")
            continue
            
        if dpub.tzinfo is None:
            dpub = dpub.replace(tzinfo=timezone.utc)
        
        age_days = (now_utc - dpub).days
        
        # Перевірка на вік (> 14 днів)
        if age_days > 14:
            logger.info(f"Відео {v_id} старше за 14 днів ({age_days} дн.) — деактивація.")
            videos_collection.update_one({"video_id": v_id}, {"$set": {"is_active": 0}})
            continue
        
        yt_count = actual_counts.get(v_id)
        if yt_count is None:
            logger.warning(f"Не отримано статистики з API для відео {v_id} — пропускаємо.")
            continue
        
        # Перевірка буферної зони (> 3 днів без росту)
        if age_days > 3 and yt_count <= db_total_comments:
            logger.info(f"Відео {v_id} у буферній зоні ({age_days} дн.) без зростання активності — деактивація.")
            videos_collection.update_one({"video_id": v_id}, {"$set": {"is_active": 0}})
            continue

        # Завантаження коментарів, якщо є активність або відео свіже
        if yt_count > db_total_comments or age_days <= 3:
            logger.info(f"Відео {v_id} активне (БД: {db_total_comments}, YT: {yt_count}) — завантаження коментарів.")
            
            last_sync = video.get("last_sync")
            
            try:
                raw_df = yt.fetch_comment(v_id, last_fetched=last_sync)
            except Exception as e:
                if "commentsDisabled" in str(e):
                    logger.warning(f"Коментарі вимкнені для відео {v_id} — деактивація.")
                    videos_collection.update_one({"video_id": v_id}, {"$set": {"is_active": 0}})
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
                        "fetched_at": now_utc
                    }
                    
                    raw_comments_collection.update_one(
                        {"comment_id": comment_id},
                        {"$set": document},
                        upsert=True
                    )
                
                new_last_date = raw_df['published_at'].max() if 'published_at' in raw_df.columns else now_utc
                
                # Оновлюємо лічильники та last_sync у колекції videos
                videos_collection.update_one(
                    {"video_id": v_id},
                    {
                        "$set": {
                            "total_comments": yt_count,
                            "last_sync": new_last_date,
                            "last_checked_at": now_utc
                        }
                    }
                )
            else:
                logger.info(f"Для відео {v_id} не виявлено нових коментарів.")
                videos_collection.update_one(
                    {"video_id": v_id},
                    {"$set": {"last_checked_at": now_utc}}
                )
    
    # Підраховуємо кількість активних відео після перевірки
    active_count = videos_collection.count_documents({"is_active": 1})
    
    # Пошук нових відео, якщо ліміт активних не заповнений
    if active_count < max_active_limit:
        slots_available = max_active_limit - active_count
        logger.info(f"Активних відео менше ліміту ({max_active_limit}) — шукаємо ще {slots_available}.")
        
        discovered_videos = yt.discover_videos_by_keyword(query_text=query_text, max_results=slots_available)
        
        for item in discovered_videos:
            v_id = item['video_id']
            existing = videos_collection.find_one({"video_id": v_id})
            if existing:
                continue
                
            pub_date = yt._parse_datetime(item['published_at']) if hasattr(yt, '_parse_datetime') else datetime.fromisoformat(item['published_at'].replace('Z', '+00:00'))
            
            video_doc = {
                "video_id": v_id,
                "channel_id": item['channel_id'],
                "title": item['title'],
                "channel_name": item['channel_name'],
                "date_publication": pub_date,
                "is_active": 1,
                "total_comments": 0,
                "last_sync": None,
                "last_checked_at": now_utc
            }
            
            videos_collection.insert_one(video_doc)
            logger.info(f"Зареєстровано нове відео в MongoDB: {item['title']} (ID: {v_id})")
    
    logger.info("--- Цикл успішно завершено ---")


def main():
    load_dotenv()
    configure_logging()
    
    QUERY_TEXT = os.getenv("MONITORING_QUERY", "Зеленський")
    MAX_ACTIVE = int(os.getenv("MAX_ACTIVE_VIDEOS", "15"))
    
    logger.info("Ініціалізація скрапера завершена.")

    try:
        run_scraper_pipeline(QUERY_TEXT, MAX_ACTIVE)
    except Exception as e:
        logger.critical(f"Критична помилка скрапера: {e}", exc_info=True)


if __name__ == "__main__":
    main()
#gcloud run jobs execute youtube-scraper-sandbox --region=europe-west1 --project=youtubepolitscarper
#^^^^thats command for run gsd scraper
