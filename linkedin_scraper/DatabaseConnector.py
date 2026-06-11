
from sqlalchemy import create_engine, text
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class Database:
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
            is_active INTEGER DEFAULT 1,
            last_checked_at TIMESTAMP,
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
            total_comments INTEGER DEFAULT 0,
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
    def register_video(self, video_id, channel_id, title, channel_name, date_publication=None, is_active=1, last_checked_at=None):
        """Insert or update channel and video metadata.

        - Upserts `channel_info` (updates channel_name if changed).
        - Upserts `video_info` (updates title/is_active/last_checked_at/date_publication when provided).
        """
        try:
            with self.engine.connect() as conn:
                # upsert channel_info
                conn.execute(text(
                    """
INSERT INTO channel_info(channel_id, channel_name)
VALUES (:c_id, :c_name)
ON CONFLICT(channel_id) DO UPDATE SET channel_name = excluded.channel_name
                    """
                ), {"c_id": channel_id, "c_name": channel_name})

                # upsert video_info - only overwrite fields when excluded values are provided
                conn.execute(text(
                    """
INSERT INTO video_info(video_id, channel_id, video_title, date_publication, is_active, last_checked_at)
VALUES (:v_id, :c_id, :title, :dpub, :is_active, :last_checked)
ON CONFLICT(video_id) DO UPDATE SET
    channel_id = excluded.channel_id,
    video_title = excluded.video_title,
    date_publication = COALESCE(excluded.date_publication, video_info.date_publication),
    is_active = excluded.is_active,
    last_checked_at = COALESCE(excluded.last_checked_at, video_info.last_checked_at)
                    """
                ), {
                    "v_id": video_id,
                    "c_id": channel_id,
                    "title": title,
                    "dpub": date_publication,
                    "is_active": is_active,
                    "last_checked": last_checked_at
                })
                conn.commit()
        except Exception as e:
            logger.exception("Failed to register video %s: %s", video_id, e)
    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            # normalize Z timezone
            v = value
            if isinstance(v, bytes):
                v = v.decode()
            if v.endswith('Z'):
                v = v[:-1] + '+00:00'
            return datetime.fromisoformat(v)
        except Exception:
            try:
                # fallback common formats
                return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
            except Exception:
                logger.debug('Unable to parse datetime: %s', value)
                return None

    def get_last_sync(self, video_id) -> Optional[datetime]:
        query = text('SELECT last_sync_date FROM video_stats WHERE video_id=:vid;')
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query, {"vid": video_id}).fetchone()
                if not result or result[0] is None:
                    return None
                return self._parse_datetime(result[0])
        except Exception as e:
            logger.exception('Failed to get last_sync for %s: %s', video_id, e)
            return None
    def update_video_stats(self, TARGET_VIDEO_ID, MODEL_ID, stats: dict, new_last_date):
        """Atomically insert or increment aggregated stats for a video+model.

        `stats` should include keys: pos, neg, neu, likes, new_total_comments
        """
        query = text("""INSERT INTO video_stats(video_id, model_id, pos_count, neg_count, neu_count, total_likes, total_comments, last_sync_date)
            VALUES(:vid, :mid, :pos, :neg, :neu, :likes, :comm, :ldate)
            ON CONFLICT(video_id, model_id) DO UPDATE SET
                pos_count = video_stats.pos_count + excluded.pos_count,
                neg_count = video_stats.neg_count + excluded.neg_count,
                neu_count = video_stats.neu_count + excluded.neu_count,
                total_comments = excluded.total_comments,
                total_likes = video_stats.total_likes + excluded.total_likes,
                last_sync_date = excluded.last_sync_date
        """)
        comm = int(stats.get('new_total_comments', 0))
        try:
            with self.engine.connect() as conn:
                conn.execute(query, {
                    "vid": TARGET_VIDEO_ID,
                    "mid": MODEL_ID,
                    "pos": int(stats.get('pos', 0)),
                    "neg": int(stats.get('neg', 0)),
                    "neu": int(stats.get('neu', 0)),
                    "likes": int(stats.get('likes', 0)),
                    "comm": comm,
                    "ldate": new_last_date
                })
                conn.commit()
        except Exception as e:
            logger.exception('Failed to update stats for %s/%s: %s', TARGET_VIDEO_ID, MODEL_ID, e)
    def get_active_videos(self):
        query = text("""
SELECT v.video_id,v.date_publication, COALESCE(s.total_comments, 0) as total_comments
FROM video_info v
LEFT JOIN video_stats s ON v.video_id = s.video_id
WHERE v.is_active = 1
                     """)
        with self.engine.connect() as conn:
            result = conn.execute(query).fetchall()
            return result 
    def deactivate_video(self,video_id):
         with self.engine.connect() as conn:
            query = text(f"UPDATE video_info SET is_active = 0 WHERE video_id = :vid")
            conn.execute(query,{"vid": video_id})
            conn.commit()
    def update_check_timestamps(self, video_ids):
        if not video_ids:
            return 
        with self.engine.connect() as conn:
            placeholders = ', '.join([f':v{i}' for i in range(len(video_ids))])
            query = text(f"UPDATE video_info SET last_checked_at = CURRENT_TIMESTAMP WHERE video_id IN ({placeholders})")

            params = {f"v{i}": vid for i, vid in enumerate(video_ids)}
            conn.execute(query, params)
            conn.commit()