
import requests
from parsel import Selector 
import sys
import logging 
import json
from tenacity import retry, wait_random, stop_after_attempt
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
from pathlib import Path
logging 
class YoutubeLoader:
    def __init__(self, video_id):
        self.env_file = Path(__file__).resolve().parent.parent / '.env'
        self.video_id = video_id 
        self._connection()
    def _connection(self):
        if self.env_file.exists():
            print('exist')
        load_dotenv(dotenv_path=self.env_file)
        API_KEY=os.getenv('YOUTUBE_MY_API_KEY')
        try:
            self.service = build('youtube','v3', developerKey=API_KEY) 
            request = self.service.commentThreads().list(
        part="snippet",
        videoId = self.video_id,
        maxResults=100,
        textFormat="plainText"
    )
            response = request.execute()
            with open('raw_comments.json', 'w', encoding='utf-8') as f:
                json.dump(response,f,ensure_ascii=False,indent=4)
            logging.info('Youtube json loaded to row_comments.json')
            logging.info('Youtube service connected')
        except Exception as e:
            print(e)
new_ex = YoutubeLoader('neYVUCDg100')