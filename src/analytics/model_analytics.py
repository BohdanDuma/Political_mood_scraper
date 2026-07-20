import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix
import plotly.express as px
import pandas as pd

def evaluate_models():
    # 1. Завантажуємо твої дані (передбачення моделей + золотий стандарт)
    df_gold = pd.read_csv('/home/bohdan/Стільниця/POLIT_SCARPER/data/manual_annotation_2026-07-14.csv') 
    df_gold = df_gold.dropna()
    print(df_gold.shape)
    name_model_col = []
    for i in df_gold.columns:
        if 'sen' in i:
            name_model_col.append(i)
    human_col_name= name_model_col.pop()
    for model in name_model_col:
        print(f"--- Звіт для {model} ---")
        print(classification_report(df_gold[f'{human_col_name}'], df_gold[f'{model}']))
        
        # 4. Зберігаємо матрицю помилок для аналізу
        cm = confusion_matrix(df_gold[f'{human_col_name}'], df_gold[f'{model}'])
        df_cm = pd.DataFrame(cm)

    # Створюємо інтерактивну карту
    fig = px.imshow(
        df_cm, 
        text_auto=True, 
        aspect="auto",
        color_continuous_scale='Blues',
        labels=dict(x="Predicted", y="Actual", color="Count")
    )
    
    fig.update_layout(
        title="Confusion Matrix (Expert vs Model)",
        xaxis_title="Передбачення моделі",
        yaxis_title="Оцінка психолога"
    )
    
    
    for model in name_model_col:
        print(f"\n--- Звіт для {model} ---")
        print(classification_report(df_gold[human_col_name], df_gold[model]))
        
        # Створення Confusion Matrix
        labels = sorted(df_gold[human_col_name].unique())
        cm = confusion_matrix(df_gold[human_col_name], df_gold[model], labels=labels)
        df_cm = pd.DataFrame(cm, index=labels, columns=labels)
        
        # Побудова графіка Plotly
        fig = px.imshow(
            df_cm, 
            text_auto=True, 
            aspect="auto",
            color_continuous_scale='Blues',
            labels=dict(x="Передбачення моделі", y="Оцінка психолога", color="Кількість"),
            title=f"Матриця помилок: {model}"
        )
        
        # Відображення графіка (якщо ти в Jupyter/Streamlit)
        fig.show()
    
   

if __name__ == "__main__":
    evaluate_models()