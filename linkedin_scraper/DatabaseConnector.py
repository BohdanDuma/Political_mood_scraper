'''import pymysql
import os
try:
    connection = pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASS'),
        database=os.getenv('DB_NAME')
    )
except:
    print('couldnt connect to db')
    '''
from sqlalchemy import create_engine, text

class Datebase:
    def __init__(self,df,db_path):
        self.df = df
        self.engine = create_engine(f"sqlite+pysqlite:///{db_path}", echo=True)
        self.create_tables()
    def create_tables(self):
        query_channel_table = """
        CREATE TABLE IF NOT EXISTS channel_info (
            channel_id VARCHAR(20) PRIMARY KEY,
            channel_ident TEXT,
            channel_name TEXT
        )
"""
        query_video_info = """
        CREATE TABLE IF NOT EXISTS video_info (
            video_id TEXT PRIMARY KEY,
            channel_id TEXT,
            video_title TEXT,
            date_publication DATETIME,
            FOREIGN KEY (channel_id) REFERENCES channel_info(channel_id)
        );
        """
        
        # 2. Довідник моделей (інформація про моделі)
        query_model_info = """
        CREATE TABLE IF NOT EXISTS model_info (
            model_id TEXT PRIMARY KEY,
            model_name TEXT,
            date_first_connection DATETIME
        );
        """
        
        # 3. Агрегована статистика (зв'язує відео та модель через складений ключ)
        query_video_stats = """
        CREATE TABLE IF NOT EXISTS video_stats (
            video_id TEXT,
            model_id TEXT,
            pos_count INTEGER DEFAULT 0,
            neg_count INTEGER DEFAULT 0,
            neu_count INTEGER DEFAULT 0,
            total_likes INTEGER DEFAULT 0,
            last_sync_date DATETIME,
            PRIMARY KEY (video_id, model_id),
            FOREIGN KEY (video_id) REFERENCES video_info(video_id)
        );
        """
        query = [query_channel_table,query_video_info,query_model_info,query_video_stats]
        with self.engine.connect() as conn:
            for q in query: 
                conn.execute(text(q))
                conn.commit()
    def register_video(self, video_id, channel_id, title, channel_name):
        with self.engine.connect() as conn:
            conn.execute(text("INSERT OR IGNORE INTO channel_info (channel_id, channel_name) VALUES (:c_id, :c_name)"),
                         {"c_id": channel_id, "c_name": channel_name})
            conn.execute(text(
                """
INSERT OR IGNORE INTO video_info(video_id, channel_id, video_title) VALUES (:v_id, :c_id, :title)
            """), {"v_id": video_id, "c_id": channel_id, "title": title})
            conn.commit()
    def get_last_sycn(self, video_id):
        query = text('SELECT last_sync_date FROM video_stats WHERE video_id=:vid;')
        with self.engine.connect() as conn:
            result = conn.execute(query, {"vid": video_id}).fetchone()
            return result[0] if result else "1900-01-01T00:00:00:00Z"
    def update_video_stats(self, TARGET_VIDEO_ID, MODEL_ID, stats, new_last_date):
        query = text("""INSERT INTO video_stats(video_id, model_id, pos_count, neg_count, neu_count, total_likes, last_sync_date)
            VALUES(:vid, :mid, :pos, :neg, :neu, :likes, :ldate)
            ON CONFLICT(video_id, model_id) DO UPDATE SET
                pos_count = pos_count + excluded.pos_count,
                neg_count = neg_count + excluded.neg_count,
                neu_count = neu_count + excluded.neu_count,
                total_likes = total_likes + excluded.total_likes,
                last_sync_date = excluded.last_sync_date
        """)
    
        with self.engine.connect() as conn:
            conn.execute(query, {
                "vid": TARGET_VIDEO_ID,
                "mid": MODEL_ID,
                "pos": stats.get('pos',0),
                "neg": stats.get('neg',0),
                "neu": stats.get('neu',0),
                "likes": stats.get('likes', 0),
                "ldate": new_last_date
            })
            conn.commit()
# Тестовий запуск
db = Datebase(None, "debug_test.db")

# КРОК 1: Перевірка реєстрації
print("Тестуємо додавання відео...")
# Додаємо спочатку канал вручну або через розширений метод
db.register_video("vid_123", "chan_789", "Зеленський: аналіз", "Новини UA")

# КРОК 2: Перевірка першого запису статистики
print("Тестуємо перший запис статистики...")
stats_v1 = {'pos': 5, 'neg': 2, 'neu': 3, 'likes': 50}
db.update_video_stats("vid_123", "transformer_v2", stats_v1, "2026-06-01T10:00:00Z")

# КРОК 3: Перевірка UPSERT (інкрементальне додавання)
print("Тестуємо інкрементальне оновлення (+5 позитивних)...")
stats_v2 = {'pos': 5, 'neg': 0, 'neu': 0, 'likes': 10}
db.update_video_stats("vid_123", "transformer_v2", stats_v2, "2026-06-01T12:00:00Z")