
from dotenv import load_dotenv
try:
    from linkedin_scraper.DataTransform import DataTransformer
    from linkedin_scraper.YouTubeLoader import YoutubeLoader
    from linkedin_scraper.DatabaseConnector import Database
    from linkedin_scraper.logging_config import configure_logging
    
    import logging
except ModuleNotFoundError:
    # allow running as a script (python linkedin_scraper/main.py)
    from DataTransform import DataTransformer
    from YouTubeLoader import YoutubeLoader
    from DatabaseConnector import Database
    from logging_config import configure_logging
    import logging
import os
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
def run_pipeline(db_path: str, query_text: str, max_active_limit: int):
    logger.info('---begin new cycle---')
    #create obj YouTubeLoader class
    db = Database(None,db_path=db_path)
    yt = YoutubeLoader()
    model_id = 'cardiffnlp/twitter-xlm-roberta-base-sentiment'
    active_videos = db.get_active_videos()
    if not active_videos:
        logger.info("in base no active video")
        video_ids = []
        actual_counts = {}
    else:
        video_ids = [v[0] for v in active_videos]
        logger.info(f'searched {len(video_ids)} videos')
        actual_counts = yt.get_actual_comment_counts(video_ids)
    processed_this_cycle = []



    for video in active_videos:
        v_id = video[0]
        dpub_raw = video[1]
        db_total_comments = video[2]

        dpub = db._parse_datetime(dpub_raw)
        if not dpub:
            logger.warning(f"Відео {v_id} має некоректну дату публікації. Пропускаємо.")
            continue
            
        # Якщо дата в базі була без часового поясу, робимо її timezone-aware (UTC)
        if dpub.tzinfo is None:
            dpub = dpub.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - dpub).days
        if age_days > 14:
            logger.info(f"Відео {v_id} старше 14 днів ({age_days} дн.). Деактивація.")
            db.deactivate_video(v_id)
            continue
        yt_count = actual_counts.get(v_id)
        
        # Якщо YouTube взагалі не повернув статистику по відео (наприклад, видалене або приватне)
        if yt_count is None:
            logger.warning(f"Не вдалося отримати лічильник для {v_id} з API. Пропускаємо.")
            continue
        if age_days > 3 and yt_count <= db_total_comments:
            logger.info(f"Відео {v_id} перебуває в буферній зоні ({age_days} дн.), але активність нульова. Деактивація.")
            db.deactivate_video(v_id)
            continue
            
        # ЕТАП 4: Збір даних (якщо відео свіже АБО є реальний приріст коментарів)
        if yt_count > db_total_comments or age_days <= 3:
            logger.info(f"Відео {v_id} активне (БД: {db_total_comments}, YT: {yt_count}). Завантажуємо нові коментарі...")
            
            # Отримуємо дату останнього успішного збору коментарів
            last_sync = db.get_last_sync(v_id)
            
            # Витягуємо нову пачку коментів з YouTube
            raw_df = yt.fetch_comment(v_id, last_fetched=last_sync)
            
            if not raw_df.empty:
                # Передаємо коментарі на ML-обробку та агрегацію метрик
                transformer = DataTransformer(raw_df)
                stats = transformer.get_aggregated_stats()
                new_last_date = transformer.get_latest_comment_date()
                
                # Замість накопичення додаванням, ми передаємо фінальний лічильник з YouTube, 
                # який метод update_video_stats перезапише через `excluded.total_comments`
                stats['new_total_comments'] = yt_count
                
                # Зберігаємо оновлену статистику в базу
                db.update_video_stats(v_id, model_id, stats, new_last_date)
                processed_this_cycle.append(v_id)
            else:
                logger.info(f"Нових коментарів для відео {v_id} не знайдено (можливо, видалені або пройшли спам-фільтр).")
                # Навіть якщо df порожній, ми додаємо ID, щоб оновити last_checked_at
                processed_this_cycle.append(v_id)
        # include publication date when registering the video
        if processed_this_cycle:
            db.update_check_timestamps(processed_this_cycle)
        still_active = db.get_active_videos()
    active_count = len(still_active) if still_active else 0
    logger.info(f"Поточна кількість активних відео на моніторингу: {active_count}")
    
    if active_count < max_active_limit:
        slots_available = max_active_limit - active_count
        logger.info(f"Кількість активних відео менша за ліміт ({max_active_limit}). Шукаємо ще {slots_available} відео...")
        
        discovered_videos = yt.discover_videos_by_keyword(query_text=query_text, max_results=slots_available)
        
        for item in discovered_videos:
            # Конвертуємо published_at з рядка YouTube в об'єкт datetime для register_video
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
            
    logger.info("--- Цикл моніторингу успішно завершено ---")
def main():
    # load environment variables from .env (so os.getenv reads them)
    load_dotenv()
    configure_logging()
    # Конфігурація Docker-ready через змінні оточення (або дефолтні значення для локалу)
    DB_PATH = os.getenv("DB_PATH", "data/youtube_analytics.db")
    QUERY_TEXT = os.getenv("MONITORING_QUERY", "Зеленський")
    MAX_ACTIVE = int(os.getenv("MAX_ACTIVE_VIDEOS", "15"))
    INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "3600"))  # За замовчуванням 1 година

    # Автоматично створюємо папку для БД (необхідно для Docker volumes)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    logger.info("Автопілот ініціалізовано. Переходимо в режим нескінченного циклу.")

    while True:
        try:
            run_pipeline(DB_PATH, QUERY_TEXT, MAX_ACTIVE)
        except Exception as e:
            # Критична помилка не повалить контейнер, а залогується з трейсбеком
            # Безпечне встановлення прапорця кольору на логгері
            try:
                setattr(logger, "colors", False)
            except Exception:
                pass
            logger.critical(f"Глобальний збій у конвеєрі: {e}", exc_info=True)

        logger.info(f"Очікування наступного циклу {INTERVAL} секунд...")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()