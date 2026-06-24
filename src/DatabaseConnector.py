from sqlalchemy import create_engine, text
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, df, db_path):
        self.df = df
        # turn off SQL echo in production-like runs; use logging for visibility
        self.engine = create_engine(f"sqlite+pysqlite:///{db_path}", echo=False)
        self.create_tables()

    def create_tables(self):
        model_table = """
        CREATE TABLE IF NOT EXISTS model_info (
            model_id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT UNIQUE,
            date_from DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """

        # 2. Інформація про канали
        query_channel_table = """
        CREATE TABLE IF NOT EXISTS channel_info (
            channel_id VARCHAR(20) PRIMARY KEY,
            channel_name TEXT
        );
        """

        # 3. Інформація про відео (Складений ключ, бо заголовок оцінюється різними моделями)
        query_video_info = """
        CREATE TABLE IF NOT EXISTS video_info (
            video_id TEXT PRIMARY KEY ,
            channel_id TEXT,
            video_title TEXT,
            date_publication DATETIME,
            is_active INTEGER DEFAULT 1,
            last_checked_at TIMESTAMP,
            FOREIGN KEY (channel_id) REFERENCES channel_info(channel_id));
        """

        # 4. Сирі коментарі (Складений ключ)
        query_create_raw_comm_table = """
        CREATE TABLE IF NOT EXISTS raw_comments(
            comment_id TEXT,
            model_id INTEGER, 
            video_id TEXT,
            comment_text TEXT,
            likes INTEGER DEFAULT 0,
            published_at DATETIME,
            sentiment_label TEXT,
            PRIMARY KEY (comment_id, model_id), 
            FOREIGN KEY (video_id) REFERENCES video_info(video_id),
            FOREIGN KEY (model_id) REFERENCES model_info(model_id)
        );
        """

        # 5. Агрегована статистика по відео та моделях
        query_video_stats = """
        CREATE TABLE IF NOT EXISTS video_stats (
            video_id TEXT,
            model_id INTEGER,
            video_title_sentiment TEXT,
            pos_count INTEGER DEFAULT 0,
            neg_count INTEGER DEFAULT 0,
            neu_count INTEGER DEFAULT 0,
            total_likes INTEGER DEFAULT 0,
            total_comments INTEGER DEFAULT 0,
            last_sync_date DATETIME,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (video_id, model_id),
            FOREIGN KEY (video_id) REFERENCES video_info(video_id),
            FOREIGN KEY (model_id) REFERENCES model_info(model_id)
        );
        """

        # 6. Глобальна статистика
        query_global_stat = """
        CREATE TABLE IF NOT EXISTS global_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER,
            snapshot_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            total_positive INTEGER,
            total_negative INTEGER,
            total_neutral INTEGER,
            total_likes INTEGER,
            total_videos INTEGER,
            total_comments INTEGER,
            FOREIGN KEY (model_id) REFERENCES model_info(model_id)
        );
        """
        query = [model_table, query_global_stat, query_create_raw_comm_table, query_channel_table, query_video_info, query_video_stats]
        with self.engine.connect() as conn:
            for q in query:
                conn.execute(text(q))
                conn.commit()
            # Migration: ensure video_title_sentiment column exists (older DBs may miss it)
            try:
                cols = conn.execute(text("PRAGMA table_info('video_stats');")).fetchall()
                col_names = [c[1] for c in cols]
                if 'video_title_sentiment' not in col_names:
                    conn.execute(text("ALTER TABLE video_stats ADD COLUMN video_title_sentiment TEXT;"))
                    conn.commit()
                    logger.info('Міграція: додано колонку video_title_sentiment у video_stats')
            except Exception as e:
                logger.debug('Міграція video_stats пропущена або не вдалася: %s', e)
            # Migration: ensure video_info has video_title_sentiment (older DBs may miss it)
            try:
                vinfo_cols = conn.execute(text("PRAGMA table_info('video_info');")).fetchall()
                vinfo_names = [c[1] for c in vinfo_cols]
                if 'video_title_sentiment' not in vinfo_names:
                    conn.execute(text("ALTER TABLE video_info ADD COLUMN video_title_sentiment TEXT;"))
                    conn.commit()
                    logger.info('Міграція: додано колонку video_title_sentiment у video_info')
            except Exception as e:
                logger.debug('Міграція video_info пропущена або не вдалася: %s', e)
            # Migration: ensure global_stats.model_id is INTEGER (not TEXT). If old schema used TEXT model identifiers, migrate rows.
            try:
                gcols = conn.execute(text("PRAGMA table_info('global_stats');")).fetchall()
                gcol_map = {c[1]: c[2].upper() for c in gcols}
                need_migrate = False
                if 'model_id' in gcol_map and gcol_map['model_id'] != 'INTEGER':
                    need_migrate = True
                if need_migrate:
                    logger.info('Міграція global_stats: приводимо model_id до INTEGER')
                    # read existing rows
                    rows = conn.execute(text('SELECT id, model_id, snapshot_date, total_positive, total_negative, total_neutral, total_likes, total_videos, total_comments FROM global_stats')).fetchall()
                    # create new table
                    conn.execute(text('''CREATE TABLE IF NOT EXISTS global_stats_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        model_id INTEGER,
                        snapshot_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                        total_positive INTEGER,
                        total_negative INTEGER,
                        total_neutral INTEGER,
                        total_likes INTEGER,
                        total_videos INTEGER,
                        total_comments INTEGER
                    );'''))
                    conn.commit()
                    # migrate rows, resolving model_id to numeric via _get_or_create_model_id
                    for r in rows:
                        old_mid = r[1]
                        try:
                            numeric_mid = self._get_or_create_model_id(old_mid)
                        except Exception:
                            numeric_mid = None
                        conn.execute(text('''INSERT INTO global_stats_new(id, model_id, snapshot_date, total_positive, total_negative, total_neutral, total_likes, total_videos, total_comments)
                            VALUES(:id, :mid, :snap, :pos, :neg, :neu, :likes, :videos, :comments)
                        '''), {
                            'id': r[0], 'mid': numeric_mid, 'snap': r[2], 'pos': r[3], 'neg': r[4], 'neu': r[5], 'likes': r[6], 'videos': r[7], 'comments': r[8]
                        })
                    conn.commit()
                    # swap tables
                    conn.execute(text('DROP TABLE global_stats;'))
                    conn.execute(text('ALTER TABLE global_stats_new RENAME TO global_stats;'))
                    conn.commit()
                    logger.info('Міграція global_stats завершена')
            except Exception as e:
                logger.debug('Міграція global_stats пропущена або не вдалася: %s', e)
            # Migration: ensure raw_comments has model_id column and composite PK (comment_id, model_id)
            try:
                rcols = conn.execute(text("PRAGMA table_info('raw_comments');")).fetchall()
                rcol_names = [c[1] for c in rcols]
                if 'model_id' not in rcol_names:
                    logger.info('Міграція raw_comments: додаємо колонку model_id і оновлюємо PK')
                    # create new table with desired schema
                    conn.execute(text('''
                        CREATE TABLE IF NOT EXISTS raw_comments_new(
                            comment_id TEXT,
                            model_id INTEGER,
                            video_id TEXT,
                            comment_text TEXT,
                            likes INTEGER DEFAULT 0,
                            published_at DATETIME,
                            sentiment_label TEXT,
                            PRIMARY KEY (comment_id, model_id),
                            FOREIGN KEY (video_id) REFERENCES video_info(video_id),
                            FOREIGN KEY (model_id) REFERENCES model_info(model_id)
                        );
                    '''))
                    conn.commit()
                    # copy existing rows, set model_id NULL
                    existing = conn.execute(text('SELECT comment_id, video_id, comment_text, likes, published_at, sentiment_label FROM raw_comments')).fetchall()
                    for row in existing:
                        conn.execute(text('''INSERT INTO raw_comments_new(comment_id, model_id, video_id, comment_text, likes, published_at, sentiment_label)
                                            VALUES(:cid, :mid, :vid, :ctext, :likes, :pub, :slabel)'''), {
                            'cid': row[0], 'mid': None, 'vid': row[1], 'ctext': row[2], 'likes': row[3], 'pub': row[4], 'slabel': row[5]
                        })
                    conn.commit()
                    # drop old and rename
                    conn.execute(text('DROP TABLE raw_comments;'))
                    conn.execute(text('ALTER TABLE raw_comments_new RENAME TO raw_comments;'))
                    conn.commit()
                    logger.info('Міграція raw_comments завершена')
            except Exception as e:
                logger.debug('Міграція raw_comments пропущена або не вдалася: %s', e)
            # Migration: ensure video_stats.model_id is INTEGER (not TEXT). Migrate if needed.
            try:
                vcols = conn.execute(text("PRAGMA table_info('video_stats');")).fetchall()
                vcol_map = {c[1]: c[2].upper() for c in vcols}
                need_migrate_vs = False
                if 'model_id' in vcol_map and vcol_map['model_id'] != 'INTEGER':
                    need_migrate_vs = True
                if need_migrate_vs:
                    logger.info('Міграція video_stats: приводимо model_id до INTEGER')
                    rows = conn.execute(text('SELECT video_id, model_id, video_title_sentiment, pos_count, neg_count, neu_count, total_likes, total_comments, last_sync_date, checked_at FROM video_stats')).fetchall()
                    conn.execute(text('''CREATE TABLE IF NOT EXISTS video_stats_new (
                        video_id TEXT,
                        model_id INTEGER,
                        video_title_sentiment TEXT,
                        pos_count INTEGER DEFAULT 0,
                        neg_count INTEGER DEFAULT 0,
                        neu_count INTEGER DEFAULT 0,
                        total_likes INTEGER DEFAULT 0,
                        total_comments INTEGER DEFAULT 0,
                        last_sync_date DATETIME,
                        checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (video_id, model_id),
                        FOREIGN KEY (video_id) REFERENCES video_info(video_id),
                        FOREIGN KEY (model_id) REFERENCES model_info(model_id)
                    );'''))
                    conn.commit()
                    for r in rows:
                        old_mid = r[1]
                        try:
                            numeric_mid = self._get_or_create_model_id(old_mid)
                        except Exception:
                            numeric_mid = None
                        conn.execute(text('''INSERT OR REPLACE INTO video_stats_new(video_id, model_id, video_title_sentiment, pos_count, neg_count, neu_count, total_likes, total_comments, last_sync_date, checked_at)
                                            VALUES(:vid, :mid, :vtitle, :pos, :neg, :neu, :likes, :comments, :last_sync, :checked)'''), {
                            'vid': r[0], 'mid': numeric_mid, 'vtitle': r[2], 'pos': r[3], 'neg': r[4], 'neu': r[5], 'likes': r[6], 'comments': r[7], 'last_sync': r[8], 'checked': r[9]
                        })
                    conn.commit()
                    conn.execute(text('DROP TABLE video_stats;'))
                    conn.execute(text('ALTER TABLE video_stats_new RENAME TO video_stats;'))
                    conn.commit()
                    logger.info('Міграція video_stats завершена')
            except Exception as e:
                logger.debug('Міграція video_stats пропущена або не вдалася: %s', e)

    def _get_or_create_model_id(self, model_identifier):
        """Return numeric model_id for given identifier (int or str). If str, insert into model_info if missing."""
        if model_identifier is None:
            return None
        # if already numeric, return as-is
        try:
            if isinstance(model_identifier, int):
                return model_identifier
            # if string containing digits only, try int
            if isinstance(model_identifier, str) and model_identifier.isdigit():
                return int(model_identifier)
        except Exception:
            pass

        # treat as model name (string)
        model_name = str(model_identifier)
        query_sel = text("SELECT model_id FROM model_info WHERE model_name = :mname;")
        with self.engine.connect() as conn:
            res = conn.execute(query_sel, {"mname": model_name}).fetchone()
            if res and res[0] is not None:
                return int(res[0])
            # insert new model record
            ins = text("INSERT INTO model_info(model_name) VALUES (:mname);")
            conn.execute(ins, {"mname": model_name})
            conn.commit()
            # fetch id
            res2 = conn.execute(query_sel, {"mname": model_name}).fetchone()
            return int(res2[0]) if res2 and res2[0] is not None else None

    def register_video(self, video_id, channel_id, title, channel_name, date_publication=None, is_active=1, last_checked_at=None):
        """Insert or update channel and video metadata.

        - Upserts `channel_info` (updates channel_name if changed).
        - Upserts `video_info` (updates title/is_active/last_checked_at/date_publication when provided).
        """
        try:
            # default last_checked_at to now (UTC) when not provided
            if last_checked_at is None:
                last_checked_at = datetime.now(timezone.utc)
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
            logger.exception("Не вдалося зареєструвати відео %s: %s", video_id, e)

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        # if a datetime object is passed, return as-is (ensure tz-aware)
        if isinstance(value, datetime):
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        # handle pandas Timestamp-like objects (have to_pydatetime)
        if hasattr(value, 'to_pydatetime'):
            try:
                dt = value.to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass
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
                logger.debug('Не вдалося розпізнати datetime: %s', value)
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
            logger.exception('Не вдалося отримати last_sync для %s: %s', video_id, e)
            return None

    def update_video_stats(self, TARGET_VIDEO_ID, MODEL_ID, stats: dict, new_last_date):
        """Atomically insert or increment aggregated stats for a video+model.

        `stats` should include keys: pos, neg, neu, likes, new_total_comments
        """
        # Ensure numeric defaults
        pos_v = int(stats.get('pos', 0))
        neg_v = int(stats.get('neg', 0))
        neu_v = int(stats.get('neu', 0))
        likes_v = int(stats.get('likes', 0))
        comm = int(stats.get('new_total_comments', 0))
        title_sent = stats.get('video_title_sentiment')

        query = text("""
INSERT INTO video_stats(video_id, model_id, video_title_sentiment, pos_count, neg_count, neu_count, total_likes, total_comments, last_sync_date)
VALUES(:vid, :mid, :tit_sent, :pos, :neg, :neu, :likes, :comm, :ldate)
ON CONFLICT(video_id, model_id) DO UPDATE SET
    video_title_sentiment = COALESCE(excluded.video_title_sentiment, video_stats.video_title_sentiment),
    pos_count = video_stats.pos_count + excluded.pos_count,
    neg_count = video_stats.neg_count + excluded.neg_count,
    neu_count = video_stats.neu_count + excluded.neu_count,
    total_comments = excluded.total_comments,
    total_likes = video_stats.total_likes + excluded.total_likes,
    last_sync_date = excluded.last_sync_date
""")

        try:
            # resolve numeric model id if a name was provided
            numeric_mid = self._get_or_create_model_id(MODEL_ID)
            with self.engine.connect() as conn:
                conn.execute(query, {
                    "vid": TARGET_VIDEO_ID,
                    "mid": numeric_mid,
                    "tit_sent": title_sent,
                    "pos": pos_v,
                    "neg": neg_v,
                    "neu": neu_v,
                    "likes": likes_v,
                    "comm": comm,
                    "ldate": new_last_date
                })
                conn.commit()
        except Exception as e:
            logger.exception('Не вдалося оновити статистику для %s/%s: %s', TARGET_VIDEO_ID, MODEL_ID, e)

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

    def deactivate_video(self, video_id):
        with self.engine.connect() as conn:
            query = text(f"UPDATE video_info SET is_active = 0 WHERE video_id = :vid")
            conn.execute(query, {"vid": video_id})
            conn.commit()

    def add_comment(self, comment_id, video_id, comment_text, likes, published_at, sentiment_label):
        """Insert or update a comment into `raw_comments`.

        - Parses `published_at` using `_parse_datetime`.
        - On conflict of `comment_id` updates text/likes/published_at/sentiment.
        """
        try:
            parsed_dt = self._parse_datetime(published_at)
            # store as ISO string if parsed, else None
            pub_val = parsed_dt.isoformat() if parsed_dt is not None else None

            query = text(
                """
INSERT INTO raw_comments(comment_id, video_id, comment_text, likes, published_at, sentiment_label)
VALUES(:cid, :vid, :ctext, :likes, :pub, :slabel)
ON CONFLICT(comment_id) DO UPDATE SET
    comment_text = excluded.comment_text,
    likes = excluded.likes,
    published_at = COALESCE(excluded.published_at, raw_comments.published_at),
    sentiment_label = excluded.sentiment_label
                """
            )

            with self.engine.connect() as conn:
                conn.execute(query, {
                    "cid": comment_id,
                    "vid": video_id,
                    "ctext": comment_text,
                    "likes": int(likes) if likes is not None else 0,
                    "pub": pub_val,
                    "slabel": sentiment_label,
                })
                conn.commit()
        except Exception as e:
            logger.exception('Не вдалося додати/оновити коментар %s: %s', comment_id, e)

    def update_check_timestamps(self, video_ids):
        if not video_ids:
            return
        with self.engine.connect() as conn:
            placeholders = ', '.join([f':v{i}' for i in range(len(video_ids))])
            query = text(f"UPDATE video_info SET last_checked_at = CURRENT_TIMESTAMP WHERE video_id IN ({placeholders})")
            params = {f"v{i}": vid for i, vid in enumerate(video_ids)}
            conn.execute(query, params)
            conn.commit()

    def global_stats_sentiment(self, model_id: str):
        query_aggregate = text("""
            WITH latest_video_stats AS (
                SELECT 
                    video_id,
                    pos_count,
                    neg_count,
                    neu_count,
                    total_likes,
                    total_comments,
                    ROW_NUMBER() OVER (PARTITION BY video_id ORDER BY checked_at DESC) as rn
                FROM video_stats
                WHERE model_id = :mid
            )
            SELECT 
                COUNT(video_id) as total_v,
                SUM(pos_count) as pos,
                SUM(neg_count) as neg,
                SUM(neu_count) as neu,
                SUM(total_likes) as likes,
                SUM(total_comments) as total_c              
            FROM latest_video_stats
            WHERE rn = 1;
        """)

        query_insert = text("""
            INSERT INTO global_stats (model_id, total_positive, total_negative, total_neutral, total_likes, total_videos, total_comments)
            VALUES (:mid, :pos, :neg, :neu, :likes, :videos, :comments)
        """)

        try:
            # resolve numeric model id to query the integer column
            numeric_mid = self._get_or_create_model_id(model_id)
            with self.engine.connect() as conn:
                # 1. Aggregate current numbers
                result = conn.execute(query_aggregate, {"mid": numeric_mid}).fetchone()

                if result and result[0] is not None:
                    videos = int(result[0])
                    pos = int(result[1] or 0)
                    neg = int(result[2] or 0)
                    neu = int(result[3] or 0)
                    likes = int(result[4] or 0)
                    comments = int(result[5] or 0)
                else:
                    videos, pos, neg, neu, likes, comments = 0, 0, 0, 0, 0, 0

                # 2. Insert snapshot into global_stats (use numeric id)
                conn.execute(query_insert, {
                    "mid": numeric_mid,
                    "pos": pos,
                    "neg": neg,
                    "neu": neu,
                    "likes": likes,
                    "videos": videos,
                    "comments": comments
                })
                conn.commit()

                return pos, neg, neu, likes, videos, comments
        except Exception as e:
            logger.exception("Не вдалося зберегти глобальні метрики настрою для моделі %s: %s", model_id, e)
            raise e

    def save_raw_comments(self, df, sentiment_labels=None, model_identifier=None):
        """Bulk insert/update comments from a pandas DataFrame.

        Parameters:
        - df: DataFrame with at least columns `comment_id`, `text` (or `textDisplay`), `likes`, `published_at`.
        - sentiment_labels: optional list of sentiment labels aligned with df rows. If omitted,
          will try to read `mood` or `sentiment_label` column from df.
        """
        try:
            if df is None or df.empty:
                return

            # Determine sentiment per-row
            if sentiment_labels is None:
                if 'mood' in df.columns:
                    sentiment_labels = df['mood'].astype(str).tolist()
                elif 'sentiment_label' in df.columns:
                    sentiment_labels = df['sentiment_label'].astype(str).tolist()
                else:
                    sentiment_labels = [None] * len(df)

            # resolve numeric model id (may insert into model_info)
            numeric_mid = self._get_or_create_model_id(model_identifier) if model_identifier is not None else None
            params_list = []
            for i, (_, row) in enumerate(df.iterrows()):
                cid = row.get('comment_id') or row.get('id')
                if cid is None:
                    continue
                text_val = row.get('text') or row.get('textDisplay') or ''
                likes = int(row.get('likes') or 0)
                pub_raw = row.get('published_at')
                parsed = self._parse_datetime(pub_raw)
                pub_val = parsed.isoformat() if parsed is not None else None
                slabel = sentiment_labels[i] if i < len(sentiment_labels) else None

                params = {
                    'cid': cid,
                    'vid': row.get('video_id') or None,
                    'ctext': text_val,
                    'likes': likes,
                    'pub': pub_val,
                    'slabel': slabel,
                    'mid': numeric_mid,
                }
                params_list.append(params)

            if not params_list:
                return

            query = text(
                """
INSERT INTO raw_comments(comment_id, model_id, video_id, comment_text, likes, published_at, sentiment_label)
VALUES(:cid, :mid, :vid, :ctext, :likes, :pub, :slabel)
ON CONFLICT(comment_id, model_id) DO UPDATE SET
    comment_text = excluded.comment_text,
    likes = excluded.likes,
    published_at = COALESCE(excluded.published_at, raw_comments.published_at),
    sentiment_label = excluded.sentiment_label
                """
            )

            with self.engine.connect() as conn:
                conn.execute(query, params_list)
                conn.commit()
        except Exception as e:
            logger.exception('Не вдалося масово зберегти сирі коментарі: %s', e)

    def _get_videos_without_sentiment(self):
        """Return list of videos (id, title) that have no computed title sentiment yet."""
        try:
            query = text("SELECT video_id, video_title FROM video_info WHERE video_title_sentiment IS NULL;")
            with self.engine.connect() as conn:
                return conn.execute(query).fetchall()
        except Exception as e:
            logger.exception("Не вдалося отримати відео без мітки настрою: %s", e)

    def backfill_title_sentiments(self, transformer):
        """
        Автоматично знаходить у базі відео без проаналізованих заголовків,
        оцінює їх через `transformer.mood_title` і оновлює записи.
        """
        logger.info("Перевірка відео без проаналізованих заголовків...")

        missing_videos = self._get_videos_without_sentiment()
        if not missing_videos:
            logger.info("Усі відео вже мають аналіз назви.")
            return

        logger.info(f"Знайдено {len(missing_videos)} відео для дозаповнення. Початок обробки...")
        for row in missing_videos:
            v_id = row[0]
            v_title = row[1]
            title_label = transformer.mood_title(v_title)
            try:
                with self.engine.connect() as conn:
                    conn.execute(
                        text("UPDATE video_info SET video_title_sentiment = :sent WHERE video_id = :vid;"),
                        {"sent": title_label, "vid": v_id}
                    )
                    conn.commit()
            except Exception as e:
                logger.error(f"Не вдалося оновити мітку для відео {v_id}: {e}")

        logger.info("Дозаповнення міток назв завершено.")
