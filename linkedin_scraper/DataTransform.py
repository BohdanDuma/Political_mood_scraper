
import requests
from parsel import Selector 
import pandas as pd
import sys
import logging 
import json
from tenacity import retry, wait_random, stop_after_attempt
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
from pathlib import Path
import jmespath
from transformers import pipeline
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
with open('raw_comments.json', 'r', encoding='utf-8') as f:
               data = json.load(f)

class DataTransformer:
    def __init__(self, raw_data):
        self.raw_data = raw_data
        self._base()
        self._preparation_data()
        self._mood_set()
    def _base(self):
            #тут використати import jmespath для того щоб витянути ті дані які потрібно
            try:
            
                jms_data = jmespath.search("items[*].{comment_id: id, author_name: snippet.topLevelComment.snippet.authorDisplayName, author_id: snippet.topLevelComment.snippet.authorChannelId.value, text: snippet.topLevelComment.snippet.textDisplay, likes: snippet.topLevelComment.snippet.likeCount, published_at: snippet.topLevelComment.snippet.publishedAt, updated_at: snippet.topLevelComment.snippet.updatedAt}", self.raw_data)
            #далі добавити трансформацію в датафрейм
            
                self.df = pd.DataFrame(jms_data)
                
            except Exception as e:
                   logging.error('Error transformation with JMES')
    def _preparation_data(self):
           self.df['likes'] = self.df['likes'].fillna(0).astype(int)
           self.df['published_at'] = pd.to_datetime(self.df['published_at'])
           self.df['updated_at'] = pd.to_datetime(self.df['updated_at'])      
           self.df['is_edited'] = self.df['published_at'] != self.df['updated_at']
    def _mood_set(self):
        texts = self.df['text'].astype(str).tolist()
        results = sentiment_pipeline(texts, truncation=True, max_length=512, batch_size=8)
        self.df['mood'] = [res['label'] for res in results]
        
    def print_df_head(self):
           print(self.df.head(10))
          
new = DataTransformer(data)
new.print_df_head()