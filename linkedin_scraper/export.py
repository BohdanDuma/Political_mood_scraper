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

def save_to_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", echo=True)
    print('done')
save_to_db()