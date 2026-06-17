
from dotenv import load_dotenv
try:
    from linkedin_scraper.DataTransform import DataTransformer
    from linkedin_scraper.YouTubeLoader import YoutubeLoader
    from linkedin_scraper.DatabaseConnector import Database
    from linkedin_scraper.logging_config import configure_logging
    
    import logging
except ModuleNotFoundError:
    # Дозволяє запускати пакет як скрипт (python linkedin_scraper/main.py)
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
    logger.info('Початок нового моніторингового циклу.')
    # Ініціалізація підсистем: база даних та завантажувач YouTube
    db = Database(None, db_path=db_path)
    yt = YoutubeLoader()
    model_id = 'cardiffnlp/twitter-xlm-roberta-base-sentiment'
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
    try:
        transformer_title = DataTransformer()
        db.backfill_title_sentiments(transformer_title)
    except Exception as e:
        logger.exception('Помилка під час заповнення пропущених міток настрою для заголовків: %s', e)


    for video in active_videos:
        v_id = video[0]
        dpub_raw = video[1]
        db_total_comments = video[2]

        dpub = db._parse_datetime(dpub_raw)
        if not dpub:
            logger.warning(f"Відео {v_id} має некоректну дату публікації — пропускаємо.")
            continue
            
        # Якщо дата в базі була без часового поясу, робимо її timezone-aware (UTC)
        if dpub.tzinfo is None:
            dpub = dpub.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - dpub).days
        if age_days > 14:
            logger.info(f"Відео {v_id} старше за 14 днів ({age_days} дн.) — деактивація.")
            db.deactivate_video(v_id)
            continue
        yt_count = actual_counts.get(v_id)
        
        # Якщо YouTube взагалі не повернув статистику по відео (наприклад, видалене або приватне)
        if yt_count is None:
            logger.warning(f"Не отримано статистики з API для відео {v_id} — пропускаємо.")
            continue
        if age_days > 3 and yt_count <= db_total_comments:
            logger.info(f"Відео {v_id} у буферній зоні ({age_days} дн.) без зростання активності — деактивація.")
            db.deactivate_video(v_id)
            continue
        

        # ЕТАП 4: Збір даних (якщо відео свіже АБО є реальний приріст коментарів)
        if yt_count > db_total_comments or age_days <= 3:
            logger.info(f"Відео {v_id} позначено як активне (БД: {db_total_comments}, YT: {yt_count}) — початок завантаження коментарів.")
            
            # Отримуємо дату останнього успішного збору коментарів
            last_sync = db.get_last_sync(v_id)
            
            # Витягуємо нову пачку коментів з YouTube із захистом від вимкнених коментарів
            try:
                raw_df = yt.fetch_comment(v_id, last_fetched=last_sync)
            except Exception as e:
                # Якщо коментарі вимкнені на стороні YouTube — деактивуємо відео
                if "commentsDisabled" in str(e):
                    logger.warning(f"Коментарі вимкнені для відео {v_id} — деактивація.")
                    db.deactivate_video(v_id)
                    continue
                # Для інших помилок піднімаємо виключення далі
                raise
            
            
            if not raw_df.empty:
                # Передаємо коментарі на ML-обробку та агрегацію метрик
                transformer = DataTransformer(raw_df)
                
                # --- ОПТИМІЗОВАНЕ ЗБЕРЕЖЕННЯ КОМЕНТАРІВ ДЛЯ KAGGLE ---
                try:
                    # Отримуємо мітки настрою (колонка 'mood' або 'sentiment_label')
                    mood_column = 'mood' if 'mood' in transformer.df.columns else 'sentiment_label'
                    sentiment_labels = transformer.df[mood_column].tolist()

                    # Додаємо `video_id` перед масовим збереженням
                    transformer.df = transformer.df.copy()
                    transformer.df['video_id'] = v_id

                    # Масове збереження коментарів (bulk insert)
                    db.save_raw_comments(transformer.df, sentiment_labels)
                except Exception as e:
                    logger.exception('Помилка масового збереження коментарів для відео %s: %s', v_id, e)
                
                # Отримуємо агреговані метрики
                stats = transformer.get_aggregated_stats()
                new_last_date = transformer.get_latest_comment_date()
                
                # Передаємо фінальний лічильник з YouTube для нового зрізу
                stats['new_total_comments'] = yt_count
                
                # Зберігаємо оновлену статистику в базу (створиться новий рядок-зріз)
                db.update_video_stats(v_id, model_id, stats, new_last_date)
                processed_this_cycle.append(v_id)
            else:
                # --- ФІКС КАРТИНКИ ДЛЯ KAGGLE (НУЛЬОВИЙ ЗРІЗ) ---
                # Якщо нових коментарів немає, ми все одно пишемо крапку в історію,
                # щоб дослідники бачили стабільний лічильник перевірок на графіку
                logger.info(f"Для відео {v_id} не виявлено нових коментарів — фіксуємо нульовий зріз.")
                
                empty_stats = {
                    'pos': 0, 'neg': 0, 'neu': 0, 'likes': 0,
                    'new_total_comments': yt_count  # Актуальна кількість з YT залишається
                }
                # Як дату синхронізації дублюємо минулу дату
                db.update_video_stats(v_id, model_id, empty_stats, last_sync)
                processed_this_cycle.append(v_id)
        # include publication date when registering the video
        # (defer updating timestamps until after processing all videos)
    # After processing all videos, update check timestamps and refresh active list
    if processed_this_cycle:
        db.update_check_timestamps(processed_this_cycle)
    still_active = db.get_active_videos()
    active_count = len(still_active) if still_active else 0
    logger.info(f"Поточна кількість активних відео на моніторингу: {active_count}")
    
    if active_count < max_active_limit:
        slots_available = max_active_limit - active_count
        logger.info(f"Кількість активних відео нижча за ліміт ({max_active_limit}) — шукаємо ще {slots_available} відео.")
        
        discovered_videos = yt.discover_videos_by_keyword(query_text=query_text, max_results=slots_available)
        
        for item in discovered_videos:
            # Конвертуємо `published_at` з рядка YouTube у datetime для `register_video`
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
    logger.info("Запис глобальних метрик настрою для поточного запуску...")
    try:
        # Передаємо назву твоєї ML моделі (наприклад, MODEL_ID)
        p, n, nu, l, v, c = db.global_stats_sentiment(model_id)
        logger.info(f"Глобальні метрики збережено — Позитив: {p}, Негатив: {n}, Нейтральні: {nu}, Лайки: {l}, Коментарів: {c}, Відео: {v}")
    except Exception as e:
        logger.error(f"Не вдалося записати глобальні метрики настрою: {e}")        
    logger.info("--- Цикл моніторингу успішно завершено ---")
def main():
    # load environment variables from .env (so os.getenv reads them)
    load_dotenv()
    configure_logging()
    # Конфігурація Docker-ready через змінні оточення (або дефолтні значення для локалу)
    DB_PATH = os.getenv("DB_PATH", "data/youtube_analytics.db")
    QUERY_TEXT = os.getenv("MONITORING_QUERY", "Зеленський")
    MAX_ACTIVE = int(os.getenv("MAX_ACTIVE_VIDEOS", "15"))
    

    # Автоматично створюємо папку для БД (необхідно для Docker volumes)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    logger.info("Ініціалізація завершена — запуск конвеєру.")

    
    try:
        run_pipeline(DB_PATH, QUERY_TEXT, MAX_ACTIVE)

    except Exception as e:
        # Критична помилка логуватиметься з трейбеком; контейнер залишиться запущеним
        try:
            setattr(logger, "colors", False)
        except Exception:
            pass
        logger.critical(f"Критична помилка конвеєру: {e}", exc_info=True)
    logger.info("Скрапер завершив роботу.")
    


if __name__ == "__main__":
    main()