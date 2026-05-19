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
        self.engine = create_engine("sqlite+pysqlite:///{db_path}", echo=True)
        self.create_tables()
    def create_tables(self):
        query_video_info = """
        CREATE TABLE IF NOT EXISTS video_info (
            video_id TEXT PRIMARY KEY,
            video_title TEXT,
            date_publication DATETIME,
            total_comments_analyzed INTEGER DEFAULT 0
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
            PRIMARY KEY (video_id, model_id)
        );
        """
        with self.engine.connect() as conn:
            conn.execute(text(query))
            conn.commit()
    def get_last_sycn(self, video_id):
        query = text('SELECT last_sync_date FROM video_stats WHERE video_id=:vid')
        with self.engine.connect() as conn:
            result = conn.execute(query, {"vid": video_id}).fetchone()
            return result[0] if result else "1900-01-01T00:00:00:00Z"
    def update_video_stats(self):
        pass
    
