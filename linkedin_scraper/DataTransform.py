
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
    def _base(self):
            #тут використати import jmespath для того щоб витянути ті дані які потрібно
            try:
                jms_data = jmespath.search("items[*].{comment_id: id, author_name: snippet.topLevelComment.snippet.authorDisplayName, author_id: snippet.topLevelComment.snippet.authorChannelId.value, text: snippet.topLevelComment.snippet.textDisplay, likes: snippet.topLevelComment.snippet.likeCount, published_at: snippet.topLevelComment.snippet.publishedAt, updated_at: snippet.topLevelComment.snippet.updatedAt}", self.raw_data)
                df = pd.DataFrame(jms_data)
                print(df['likes'].notna().count())
            except Exception as e:
                   logging.error('Error transformation with JMES')
            
            #далі добавити трансформацію в датафрейм
            
new = DataTransformer(data)