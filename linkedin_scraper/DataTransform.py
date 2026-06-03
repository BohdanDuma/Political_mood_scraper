
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
class DataTransformer:
    
    def __init__(self, raw_data):
        self.df = raw_data
        if not self.df.empty:
            self._preparation_data()
            self._mood_set()
        else:
            logging.warning('empty dataframe from youtube')
 
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
           print(self.df.columns)
          
