
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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s%(levelname)s%(message)s',
    handlers=[
        logging.FileHandler("YT_project.log"),
        logging.StreamHandler()
    ]
)
with open('raw_comments.json', 'r', encoding='utf-8') as f:
               data = json.loads(f)

class DataTransformer:
    def __init__(self, raw_data):
        self.raw_data = raw_data
        self._base()
    def _base(self):
            
            print(self.raw_data)
new = DataTransformer(data)