import pandas as pd
import os
# 1. Завантажуємо твій датасет
'''df = pd.read_csv('/home/bohdan/Стільниця/POLIT_SCARPER/data/manual_annotation.csv')

# 2. Створюємо словник для заміни
replace_dict = {
    'n': 'negative',
    'ne': 'neutral',
    'p': 'positive'
}

# 3. Замінюємо літери на слова строго в колонці 'human_sentiment'
df['human_sentiment'] = df['human_sentiment'].replace(replace_dict)
df.to_csv('/home/bohdan/Стільниця/POLIT_SCARPER/data/manual_annotation_2026-07-14.csv')'''

df = pd.read_csv('/home/bohdan/Стільниця/POLIT_SCARPER/data/manual_annotation_2026-07-14.csv')
df_twoFP = df[(df['sentiment_model_1'] == 'positive') & 
              (df['sentiment_model_2'] == 'positive') & 
              (df['human_sentiment'] == 'negative')]
df_twoFN = df[(df['sentiment_model_1'] == 'negative') & 
              (df['sentiment_model_2'] == 'negative') & 
              (df['human_sentiment'] == 'positive')]
 
output_path = "/home/bohdan/Стільниця/POLIT_SCARPER/data/output.txt"
pd.set_option('display.max_colwidth', None)
pd.set_option('display.max_rows', None)
#Запис коментарів де дві моделі дали протилежний результат до людської розмітки
try:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("Перевірка запису:\n")
        f.write(f"False Positives знайдено: {len(df_twoFP)}\n")
        f.write(df_twoFP['comment_text'].to_string(index=False))
        f.write("\n\n--- False Negatives ---\n")
        f.write(df_twoFN['comment_text'].to_string(index=False))
    
    print(f"Файл успішно створено за адресою: {output_path}")
    print(f"Вміст файлу можна перевірити командою в терміналі: cat '{output_path}'")
    
except Exception as e:
    print(f"Сталася помилка при записі файлу: {e}")