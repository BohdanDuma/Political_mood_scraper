'''import pymysql
import os
try:
    connection = pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASS'),
        database=os.getenv('DB_NAME')
    )
except:
    print('couldnt connect to db')
    '''
from sqlalchemy import create_engine

class Datebase:
    def __init__(self,df):
        self.df = df
    def stat_calc(self):
        self.df     
    def save_to_db(db):
        engine = create_engine("sqlite+pysqlite:///:memory:", echo=True)
        texts = db['text'].astype(str).tolist()
        print('done')
    def get_last_sycn(self):
        pass
    def update_video_stats(self):
        pass
    
save_to_db()