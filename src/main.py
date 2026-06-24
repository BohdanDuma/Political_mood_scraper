
from dotenv import load_dotenv
try:
    from src.DataTransform import DataTransformer
    from src.YouTubeLoader import YoutubeLoader
    from src.DatabaseConnector import Database
    from src.logging_config import configure_logging
    
    import logging
except ModuleNotFoundError:
    from src.DataTransform import DataTransformer
    from src.YouTubeLoader import YoutubeLoader
    from src.DatabaseConnector import Database
    from src.logging_config import configure_logging
    import logging
import os
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def run_pipeline(db_path: str, query_text: str, max_active_limit: int, model_ids: list = None):
    logger.info('Початок нового моніторингового циклу.')
    # Ініціалізація моделей: читаємо з оточення або використовуємо дефолт
    if model_ids is None:
        model_ids = [
            'cardiffnlp/twitter-xlm-roberta-base-sentiment',
            'nlptown/bert-base-multilingual-uncased-sentiment'
        ]
    
    from src.ModelManager import ModelFactory
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
    
    # Ініціалізація підсистем
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
    try:
        for model_name, model in models.items():
            logger.info(f"Запуск backfill для моделі: {model_name}")
            transformer_title = DataTransformer(model=model)
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
            logger.info(f"Відео {v_id} позначено як активне (БД: {db_total_comments}, YT: {yt_count}) — початок завантаження коментарів.")
            
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
                # ОБРОБКА З ТРЬОМА МОДЕЛЯМИ
                for model_name, sentiment_model in models.items():
                    logger.info(f"Обробка коментарів для {v_id} моделлю {model_name}")
                    transformer = DataTransformer(raw_df.copy(), model=sentiment_model)
                    
                    try:
                        mood_column = 'mood' if 'mood' in transformer.df.columns else 'sentiment_label'
                        sentiment_labels = transformer.df[mood_column].tolist()
                        transformer.df = transformer.df.copy()
                        transformer.df['video_id'] = v_id
                        db.save_raw_comments(transformer.df, sentiment_labels, model_name)
                    except Exception as e:
                        logger.exception('Помилка масового збереження коментарів для %s моделлю %s: %s', v_id, model_name, e)
                    
                    stats = transformer.get_aggregated_stats()
                    new_last_date = transformer.get_latest_comment_date()
                    stats['new_total_comments'] = yt_count
                    db.update_video_stats(v_id, model_name, stats, new_last_date)
                    logger.info(f"Статистика для {v_id} (модель: {model_name}) оновлена")
                
                processed_this_cycle.append(v_id)
            else:
                logger.info(f"Для відео {v_id} не виявлено нових коментарів — фіксуємо нульовий зріз.")
                
                empty_stats = {
                    'pos': 0, 'neg': 0, 'neu': 0, 'likes': 0,
                    'new_total_comments': yt_count
                }
                for model_name in models.keys():
                    db.update_video_stats(v_id, model_name, empty_stats, last_sync)
                processed_this_cycle.append(v_id)

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
    
    logger.info("Запис глобальних метрик настрою для всіх моделей...")
    try:
        for model_id in model_ids:
            p, n, nu, l, v, c = db.global_stats_sentiment(model_id)
            logger.info(f"[{model_id}] Позитив: {p}, Негатив: {n}, Нейтральні: {nu}, Лайки: {l}, Коментарів: {c}, Відео: {v}")
    except Exception as e:
        logger.error(f"Не вдалося записати глобальні метрики настрою: {e}")        
    
    logger.info("--- Цикл моніторингу успішно завершено ---")


def main():
    load_dotenv()
    configure_logging()
    
    DB_PATH = os.getenv("DB_PATH", "data/youtube_analytics.db")
    QUERY_TEXT = os.getenv("MONITORING_QUERY", "Зеленський")
    MAX_ACTIVE = int(os.getenv("MAX_ACTIVE_VIDEOS", "15"))
    
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    logger.info("Ініціалізація завершена — запуск конвеєру.")

    try:
        run_pipeline(DB_PATH, QUERY_TEXT, MAX_ACTIVE)
    except Exception as e:
        try:
            setattr(logger, "colors", False)
        except Exception:
            pass
        logger.critical(f"Критична помилка конвеєру: {e}", exc_info=True)
    
    logger.info("Скрапер завершив роботу.")


if __name__ == "__main__":
    main()
