
import requests
from parsel import Selector 
import sys
import logging 
from tenacity import retry, wait_random, stop_after_attempt
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
from pathlib import Path
class YoutubeLoader:
    def __init__(self):
        self.env_file = Path(__file__).resolve().parent.parent / '.env'

        def _connection(self):
            if self.env_file.exists():
                print('exict')

            load_dotenv(dotenv_path=self.env_file)
            API_KEY=os.getenv('YOUTUBE_MY_API_KEY')
            try:
                self.service = build('youtube','v3', developerKey=API_KEY) 
                logging.info('Youtube service connected')
            except Exception as e:
                print(e)