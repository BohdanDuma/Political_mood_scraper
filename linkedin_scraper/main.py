from DataTransform import DataTransformer 
from YouTubeLoader import YoutubeLoader
from DatabaseConnector import Database
import logging 

def main():
    #create obj YouTubeLoader class
    loader = YoutubeLoader()
    db = Database(None,"politics_monitor.db")
    discover_videos = loader.discover_videos_by_keyword('Зеленський', max_results = 10)
    for video in discover_videos:
        v_id = video['video_id']
        v_title = video['title']

        # include publication date when registering the video
        db.register_video(v_id, video['channel_id'], v_title, video['channel_name'], video.get('published_at'))
        last_date = db.get_last_sync(v_id)
        df_raw = loader.fetch_comment(v_id, last_fetched=last_date)
        if not df_raw.empty:
            transformer = DataTransformer(df_raw)
            stats = transformer.get_aggregated_stats()
            new_sync_date = transformer.get_latest_comment_date()
            db.update_video_stats(v_id, "roberta_v1", stats, new_sync_date)
            logging.info(f'{v_title} completed. Stat: {stats}')
if __name__ == "__main__":
    main()