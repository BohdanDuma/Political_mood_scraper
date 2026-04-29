
import requests
from parsel import Selector 
import sys
import logging 
from tenacity import retry, wait_random, stop_after_attempt
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
from pathlib import Path
env_file = Path(__file__).resolve().parent.parent / '.env'

if env_file.exists():
    print('exict')

load_dotenv(dotenv_path=env_file)
API_KEY=os.getenv('YOUTUBE_MY_API_KEY')
try:
    service = build('youtube','v3', developerKey=API_KEY) 
    print(service)
except Exception as e:
    print(e)