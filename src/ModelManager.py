import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from transformers import pipeline

logger = logging.getLogger(__name__)


class SentimentModel(ABC):
    """Абстрактний інтерфейс для моделі аналізу тональності"""
    
    @abstractmethod
    def predict(self, texts: List[str], batch_size: int = 8) -> List[str]:
        """Повернути список міток у стандартному форматі: positive/negative/neutral"""
        pass
    
    @abstractmethod
    def predict_single(self, text: str) -> str:
        """Одиночне передбачення"""
        pass
    
    @property
    @abstractmethod
    def model_id(self) -> str:
        """ID моделі"""
        pass


class HFTransformersAdapter(SentimentModel):
    """Адаптер для HuggingFace transformers pipeline"""
    
    def __init__(self, model_name: str, device: int = -1):
        self._model_name = model_name
        self._device = device
        self._pipeline = None
        self._load_model()
    
    def _load_model(self):
        """Lazy loading моделі при першому використанні"""
        try:
            logger.info(f"Завантаження моделі: {self._model_name}")
            self._pipeline = pipeline(
                'sentiment-analysis',
                model=self._model_name,
                device=self._device
            )
            logger.info(f"Модель {self._model_name} успішно завантажена")
        except Exception as e:
            logger.error(f"Помилка завантаження моделі {self._model_name}: {e}")
            raise
    
    def predict(self, texts: List[str], batch_size: int = 8) -> List[str]:
        """Батч-передбачення з нормалізацією міток"""
        if not texts:
            return []
        
        try:
            results = self._pipeline(texts, truncation=True, max_length=512, batch_size=batch_size)
            normalized = [self._normalize_label(res['label']) for res in results]
            return normalized
        except Exception as e:
            logger.error(f"Помилка під час передбачення: {e}")
            return ['neutral'] * len(texts)
    
    def predict_single(self, text: str) -> str:
        """Одиночне передбачення"""
        try:
            result = self._pipeline(text, truncation=True, max_length=512)
            return self._normalize_label(result[0]['label'])
        except Exception as e:
            logger.error(f"Помилка під час передбачення: {e}")
            return 'neutral'
    
    @staticmethod
    def _normalize_label(raw_label: str) -> str:
        """Конвертувати різні формати міток у унітарний"""
        mapping = {
            'LABEL_0': 'negative',  'negative': 'negative',
            'LABEL_1': 'neutral',   'neutral': 'neutral',
            'LABEL_2': 'positive',  'positive': 'positive',
            "1 star": "negative", "2 stars": "negative", "3 stars": "neutral", "4 stars": "positive", "5 stars": "positive"
        }
        return mapping.get(raw_label, 'neutral')
    
    @property
    def model_id(self) -> str:
        return self._model_name


class ModelFactory:
    """Фабрика для створення або повернення кешованих  моделей"""
    
    _cache: Dict[str, SentimentModel] = {}
    
    @classmethod
    def get_model(cls, model_id: str, device: int = -1) -> SentimentModel:
        """Отримати адаптер (з кешу або створити новий)"""
        if model_id not in cls._cache:
            logger.info(f"Створення нового адаптера для моделі: {model_id}")
            cls._cache[model_id] = HFTransformersAdapter(model_id, device=device)
        return cls._cache[model_id]
    
    @classmethod
    def clear_cache(cls):
        """Очистити кеш моделей"""
        cls._cache.clear()
        logger.info("Кеш моделей очищено")
    
    @classmethod
    def list_cached(cls) -> List[str]:
        """Список кешованих моделей"""
        return list(cls._cache.keys())
