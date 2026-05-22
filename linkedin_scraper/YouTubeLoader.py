
import logging 
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
from pathlib import Path
logging 
class YoutubeLoader:
    def __init__(self):
        self.env_file = Path(__file__).resolve().parent.parent / '.env'
        self.service=None
        self._connection()
    def _connection(self):
        if self.env_file.exists():
            print('exist')
        load_dotenv(dotenv_path=self.env_file)
        API_KEY=os.getenv('YOUTUBE_MY_API_KEY')
        try:
            self.service = build('youtube','v3', developerKey=API_KEY) 
            logging.INFO('You tube connected!')
        except Exception as e:
            print(e)
            logging.error(f'{e} YouTube not connection ')
            logging.info('Youtube service connected')
        
    def fetch_comment(self):
        if not self.service:
            logging.error("YouTube service not connected")
            return pd.DataFrame()
        new_comments = []
        next_page_tosken = None

        while True:
            try:
                request = self.service.commentThreads().list(
        part="snippet",
        videoId=video_id,
        maxResults=100,
        textFormat="plainText"
    )
            response = request.execute()
            stop_fetching = False
            items = response.get('items',[])

            if not items:
                break
            

new_ex = YoutubeLoader('neYVUCDg100')