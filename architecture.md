```mermaid
graph TD
    %% Планувальник
    Anacron[Anacron / ОС] -->|Щодня запускає| Main[main.py / run_pipeline]

    %% Зовнішні сервіси
    subgraph External [Зовнішні сервіси]
        YTAPI[YouTube Data API]
        HHF[Hugging Face Hub]
    end

    %% Основні компоненти (Моноліт)
    subgraph Monolith [Поточний Монолітний Скрипт]
        Main -->|1. Перевіряє активні відео| DB[(Database / SQLite)]
        Main -->|2. Отримує нову статистику та коментарі| YT[YouTubeLoader]
        
        YT -->|Запитує API| YTAPI

        Main -->|3. Завантажує важкі моделі| MM[ModelManager / Factory]
        MM -->|Завантажує ваги| HHF

        Main -->|4. Передає сирий текст і модель| DT[DataTransformer]
        DT -->|Інференс PyTorch / Transformers| DT

        DT -->|5. Повертає результати та статистику| DB
    end

    %% Логування
    Main -.->|Пише логи| Log[YT_project.log]
