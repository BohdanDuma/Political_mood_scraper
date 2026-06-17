
from parsel import Selector 
import pandas as pd
import logging 
from tenacity import retry, wait_random, stop_after_attempt
from googleapiclient.discovery import build
from dotenv import load_dotenv
from pathlib import Path

from transformers import pipeline
from datetime import datetime, timezone

model_name = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
sentiment_pipeline = pipeline('sentiment-analysis', model=model_name, device=-1)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s%(levelname)s%(message)s',
    handlers=[
        logging.FileHandler("YT_project.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
class DataTransformer:
    
    def __init__(self, raw_data=pd.DataFrame()):
        self.df = raw_data
        if not self.df.empty:
            self._preparation_data()
            self._mood_set()
        else:
            logger.warning('Отримано порожній DataFrame з YouTube — обробка пропущена')
 
    def _preparation_data(self):
        self.df['likes'] = self.df['likes'].fillna(0).astype(int)
        self.df['published_at'] = pd.to_datetime(self.df['published_at'])
        if 'updated_at' in self.df.columns:
            self.df['updated_at'] = pd.to_datetime(self.df['updated_at'])      
            self.df['is_edited'] = self.df['published_at'] != self.df['updated_at']
        else:
            self.df['is_edited'] = False
    
    def _mood_set(self):
        texts = self.df['text'].astype(str).tolist()
        
        results = sentiment_pipeline(texts, truncation=True, max_length=512, batch_size=8)
        self.df['mood'] = [res['label'] for res in results]
        
    def get_aggregated_stats(self):
        if self.df.empty:
            return {'pos': 0, 'neg': 0, 'neu': 0, 'likes': 0, 'new_last_date': "1900-01-01T00:00:00Z"}
        mood_counts = self.df['mood'].value_counts()
        stats = {
        'pos': int(mood_counts.get('positive', mood_counts.get('LABEL_2', 0))),
        'neg': int(mood_counts.get('negative', mood_counts.get('LABEL_0', 0))),
        'neu': int(mood_counts.get('neutral', mood_counts.get('LABEL_1', 0))),
        'likes': int(self.df['likes'].sum())
    }
        return stats
    def get_latest_comment_date(self):
        if self.df.empty:
            return datetime(1900, 1, 1, tzinfo=timezone.utc)
        latest_date = self.df['published_at'].max()
        # convert pandas Timestamp to python datetime
        if isinstance(latest_date, pd.Timestamp):
            dt = latest_date.to_pydatetime()
        else:
            dt = latest_date
        if dt is None:
            return datetime(1900, 1, 1, tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    def mood_title(self, video_title):
        if not video_title:
            return 'neutral'

        # Підтримуємо як одиночні заголовки, так і списки заголовків (батч)
        is_single_string = isinstance(video_title, str)
        titles_list = [video_title] if is_single_string else list(video_title)

        # Гарантуємо строковий тип для кожного елементу
        titles_list = [str(t) for t in titles_list]

        try:
            # Оцінюємо тональність заголовків пачкою
            results = sentiment_pipeline(titles_list, truncation=True, max_length=512, batch_size=8)

            # Мапінг міток до уніфікованого формату бази
            label_mapping = {
                'LABEL_0': 'negative', 'negative': 'negative',
                'LABEL_1': 'neutral',  'neutral': 'neutral',
                'LABEL_2': 'positive', 'positive': 'positive'
            }

            cleaned_labels = [label_mapping.get(res['label'], res['label']) for res in results]

            # Повертаємо рядок для одиночного запиту або список для батчу
            return cleaned_labels[0] if is_single_string else cleaned_labels

        except Exception as e:
            logger.exception('Помилка під час оцінки настрою заголовку: %s', e)
            return 'neutral' if is_single_string else ['neutral'] * len(titles_list)