
import logging
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
from pathlib import Path
import pandas as pd
import json
from datetime import datetime, timezone
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
 
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
    @retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(5), retry=retry_if_exception_type(Exception), reraise=True)
    def get_actual_comment_counts(self, video_ids: list) -> dict:
        if not self.service or not video_ids:
            return {}
        results = {}
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]
            try:
                request = self.service.videos().list(
                    part="statistics",
                    id=",".join(batch)
                )
                response = request.execute()
                for item in response.get("items", []):
                    vid_id = item["id"]
                    comment_count = int(item["statistics"].get("commentCount", 0))
                    results[vid_id] = comment_count
            except Exception as e:
                logging.error(f"Batch stats fetching error: {e}")
                raise

        return results
    @retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(5), retry=retry_if_exception_type(Exception), reraise=True)
    def discover_videos_by_keyword(self, query_text='Зеленський', max_results = 5):
        if not self.service:
            return []
        request = self.service.search().list(
            part="snippet",
            q=query_text,
            maxResults=max_results,
            order="date",
            type="video",
            relevanceLanguage="uk"
        )
        response = request.execute()
        discovered = []
        for item in response.get('items', []):
            if item['id'].get('kind') == 'youtube#video':
                discovered.append({
                    'video_id': item['id']['videoId'],
                    'title': item['snippet']['title'],
                    'channel_id': item['snippet']['channelId'],
                    'channel_name': item['snippet']['channelTitle'],
                    'published_at': item['snippet']['publishedAt']
                })
        return discovered
    @retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(3), retry=retry_if_exception_type(Exception), reraise=True)
    def fetch_comment(self, video_id, last_fetched=None, max_pages=3):
        #if there are no comments from this video in the database
        '''cache_path = Path(f'cache_{video_id}.parquet')
        if cache_path.exists():
            print(f"Download Paruet-cache to: {cache_path}")
            return pd.read_parquet(cache_path)'''
        if last_fetched is None:
            last_fetched = datetime(1900, 1, 1, tzinfo=timezone.utc)
        elif isinstance(last_fetched, str):
            last_fetched = datetime.fromisoformat(last_fetched.replace('Z', '+00:00'))
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
                
                items = response.get('items', [])
                if not items:
                    break
                stop_fetching = False
                for item in items:
                    snippet = item.get('snippet', {}).get('topLevelComment', {}).get('snippet', {})
                    published_at_str = snippet.get('publishedAt')
                    if not published_at_str:
                        continue
                    try:
                        published_at = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
                    except Exception:
                        # skip unparsable timestamps
                        continue
                    if published_at > last_fetched:
                        new_comments.append({
                            'comment_id': item.get('id'),
                            'text': snippet.get('textDisplay', ''),
                            'likes': int(snippet.get('likeCount', 0)),
                            'published_at': published_at
                        })
                    else:
                        stop_fetching = True
                        break
                if stop_fetching:
                    break
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
                pages_processed += 1
            except Exception as e:
            # Перетворюємо помилку в рядок лише для внутрішньої перевірки
                err_str = str(e)
            
                if "commentsDisabled" in err_str:
                # Це звичайна ситуація, пишемо спокійне попередження без деталей
                    logging.warning(f"Коментарі вимкнено для відео {video_id} (перевірка в Loader)")
                else:
                # Це реальна проблема (інтернет, квота тощо). 
                # Пишемо ERROR, але САМ КЛЮЧ НЕ ВИВОДИМО (прибрали {e})
                    logging.error(f"API Error while fetching comments for {video_id} (Перевірте квоту або мережу)")
                raise e
        df_final = pd.DataFrame(new_comments)
        '''if not df_final.empty:
            df_final.to_parquet(cache_path,index=False)
            print(f'DataFrame saved to Parquet')'''
        return df_final    
