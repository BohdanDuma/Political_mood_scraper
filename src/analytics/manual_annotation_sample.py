import os
import sqlite3
import pandas as pd
import shutil
from datetime import datetime
import kagglehub
from dotenv import load_dotenv
from sklearn.model_selection import train_test_split

load_dotenv()
 
DB_PATH = os.getenv("DB_PATH")
EXPORT_DIR = os.getenv("EXPORT_DIR")
DATASET_HANDLE = os.getenv("DATASET_HANDLE")

def db_connection():
    print(f"[{datetime.now()}]Початок формування вибірки для ручного маркування.")

    if not all([DB_PATH, EXPORT_DIR]):
        print("Помилка: Перевірте .env файл! Відсутній DB_PATH, EXPORT_DIR")
        return

    if not os.path.exists(DB_PATH):
        print(f"Помилка: База даних {DB_PATH} не знайдена!")
        return
        

    if os.path.exists(EXPORT_DIR):
        shutil.rmtree(EXPORT_DIR)
    os.makedirs(EXPORT_DIR, exist_ok=True)
   
    conn = sqlite3.connect(DB_PATH)
    try:
        print("Формування датафрейму...")
        #take 50 more popular video 
        high_popular_vid = pd.read_sql_query("WITH TopVideos AS(SELECT video_id FROM video_stats ORDER BY total_likes DESC, total_comments DESC LIMIT 50)SELECT video_id,comment_id, comment_text, likes, MAX(CASE WHEN model_id = 1 THEN sentiment_label END) AS sentiment_model_1, MAX(CASE WHEN model_id = 2 THEN sentiment_label END) AS sentiment_model_2 FROM raw_comments WHERE video_id IN (SELECT video_id FROM TopVideos) GROUP BY comment_id, comment_text, likes;", conn)
        if not high_popular_vid.empty:
            print('df is created')
            return high_popular_vid
    except Exception as e:
        print(f"помилка при експорті основних даних: {e}")
    finally:
        conn.close()
def strat_sample_maker(df):
    try: 
        if df is None or df.empty:
            print("Датафрейм порожній.")
            return None 
        
        medians = df.groupby('video_id')['likes'].transform('median')
       
        df['is_top'] = df['likes'] >= medians
        df['pop_str'] = df['is_top'].map({True: 'Top', False: 'Bottom'})
        df['strata'] = df['sentiment_model_1'] + '_' + df['sentiment_model_2'] + '_' + df['pop_str'] 
        
        print(df['strata'].value_counts())
    
    except Exception as e:
        print(f"помилка при формуванні вибірк: {e}")
    try:
        sample_df, _ = train_test_split(
            df, 
            train_size=300, 
            stratify=df['strata'], 
            random_state=42
        )
        print(f"Вибірку сформовано: {len(sample_df)} рядків.")
        return sample_df
    except ValueError as e:
        print(f"Помилка стратифікації (можливо, мало даних для певного класу): {e}")
        return df
def main():
    df = db_connection()
    sample= strat_sample_maker(df)
    print(sample.head())
    print("Стратифіковану вибірку з 300 екземплярів сформовано")
    sample['human_sentiment'] = "" 
    sample['is_sarcasm'] = False
    sample.to_csv('data/data for manual')
if __name__ == "__main__":
    main()