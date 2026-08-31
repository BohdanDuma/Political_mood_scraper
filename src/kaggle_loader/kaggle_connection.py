import os
import sqlite3
import pandas as pd
import shutil
from datetime import datetime
import kagglehub
from dotenv import load_dotenv

load_dotenv()
 
DB_PATH = os.getenv("DB_PATH")
EXPORT_DIR = os.getenv("EXPORT_DIR")
DATASET_HANDLE = os.getenv("DATASET_HANDLE")

def main():
    print(f"[{datetime.now()}] Запуск авто-публікації на Kaggle...")

    if not all([DB_PATH, EXPORT_DIR, DATASET_HANDLE]):
        print("Помилка: Перевірте .env файл! Відсутній DB_PATH, EXPORT_DIR або DATASET_HANDLE.")
        return

    if not os.path.exists(DB_PATH):
        print(f"Помилка: База даних {DB_PATH} не знайдена!")
        return
        

    if os.path.exists(EXPORT_DIR):
        shutil.rmtree(EXPORT_DIR)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    
    
   
    conn = sqlite3.connect(DB_PATH)
    try:
        print("Експорт обов'язкових таблиць у CSV...")
        

        df_videos = pd.read_sql_query("SELECT * FROM video_info", conn)
        df_videos.to_csv(os.path.join(EXPORT_DIR, "videos.csv"), index=False)
        
        df_comments = pd.read_sql_query("SELECT * FROM raw_comments", conn)
        df_comments.to_csv(os.path.join(EXPORT_DIR, "comments.csv"), index=False)

        try:
            df_stats = pd.read_sql_query("SELECT * FROM global_stats", conn)
            df_stats.to_csv(os.path.join(EXPORT_DIR, "global_sum.csv"), index=False)
            print("-> global_stats експортовано.")
        except Exception as e:
            print(f"Попередження: Пропущено global_stats ({e})")
        try:
            shutil.copy("/home/bohdan/Стільниця/POLIT_SCARPER/data/manual_annotation_2026-07-14.csv", os.path.join(EXPORT_DIR, "manual_annotation_2026-07-14.csv"))
            print("-> manual_annotation_2026-07-14.csv успішно додано до експорту.")
        except Exception as e:
            print(f"Помилка копіювання золотого стандарту: {e}")    
        try:
            df_model = pd.read_sql_query("SELECT * FROM model_info", conn)
            df_model.to_csv(os.path.join(EXPORT_DIR, "model_info.csv"), index=False)
            print("-> model_info експортовано.")
        except Exception as e:
            print(f"Попередження: Пропущено model_info ({e})")
       
        print("Експорт таблиць завершено успішно.")
        try:
            shutil.copy(DB_PATH, os.path.join(EXPORT_DIR, os.path.basename(DB_PATH)))
        except Exception as e:
            print("Не можу додати базу даних" )
    except Exception as e:
        print(f"Критична помилка при експорті основних даних: {e}")
        return
    finally:
        conn.close()


    try:
        note = f"Auto-update: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        print(f"Синхронізація з Kaggle ({DATASET_HANDLE})...")
         
        kagglehub.dataset_upload(
            DATASET_HANDLE,
            EXPORT_DIR,
            version_notes=note
        )
        print("🎉 Датасет успішно оновлено на Kaggle!")
    except Exception as e:
        print(f"Помилка завантаження через kagglehub: {e}")

if __name__ == "__main__":
    main()