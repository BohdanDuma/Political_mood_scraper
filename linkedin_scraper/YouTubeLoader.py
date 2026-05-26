
import logging 
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
from pathlib import Path
import pandas as pd
import json
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
            logging.info('You tube connected!')
        except Exception as e:
            print(e)
            logging.error(f'{e} YouTube not connection ')
            logging.info('Youtube service connected')
        
    def fetch_comment(self, video_id, last_fetched=None, max_pages=3):
        #if there are no comments from this video in the database
        cache_path = Path(f'cache_{video_id}.parquet')
        if cache_path.exists():
            print(f"Download Paruet-cache to: {cache_path}")
            return pd.read_parquet(cache_path)
        if last_fetched is None:
            last_fetched = "1900-01-01T00:00:00Z"
        #if there are no response from API 
        if not self.service:
            logging.error("YouTube service not connected")
            return pd.DataFrame()
        new_comments = []
        next_page_token=None
        pages_processed = 0 
        while pages_processed < max_pages:
            try:
                request = self.service.commentThreads().list(
        part="snippet",
        videoId=video_id,
        maxResults=100,
        order='time',
        textFormat="plainText",
        pageToken=next_page_token
    )
                response = request.execute()
                
                items = response.get('items',[])

                if not items: break
                stop_fetching = False
                for item in items:
                    snippet = item['snippet']['topLevelComment']['snippet']
                    published_at = snippet['publishedAt']
                    if published_at > last_fetched:
                        new_comments.append({
                            'comment_id': item['id'],
                            'text': snippet['textDisplay'],
                            'likes': snippet['likeCount'],
                            'published_at': published_at
                        })
                    else:
                        stop_fetching = True
                        break
                if stop_fetching:
                    break        
                next_page_token= response.get('nextPageToken')
                if not next_page_token:
                    break
                #add count to processed pages
                pages_processed += 1
            except Exception as e:
                print(f'API Error: {e}')
        df_final = pd.DataFrame(new_comments)
        if not df_final.empty:
            df_final.to_parquet(cache_path,index=False)
            print(f'DataFrame saved to Parquet')
        return df_final    
new_ex = YoutubeLoader()
res = new_ex.fetch_comment('neYVUCDg100' )
print(res)