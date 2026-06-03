from DataTransform import DataTransformer 
from YouTubeLoader import YoutubeLoader
from DatabaseConnector import Database


def main():
    #create obj YouTubeLoader class
    loader = YoutubeLoader()
    db = Database("politics_monitor.db")
    discover_videos = loader.discover_videos_by_keyword('Зеленський', max_results = 10)
    for video in discover_videos:
        v_id = video['video_id']
        v_title = video['title']

        db.register_video(v_id, video['channel_id'],v_title, video['channel_name'])
if __name__ == "__main__":
    main