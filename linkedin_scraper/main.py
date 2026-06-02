from DataTransform import DataTransformer 
from YouTubeLoader import YoutubeLoader
from DatabaseConnector import Database


def main():
    #create obj YouTubeLoader class
    loader = YoutubeLoader()
    db = Database("politics_monitor.db")
if __name__ == "__main__":
    main