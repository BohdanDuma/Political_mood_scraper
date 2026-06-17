import logging


def configure_logging(log_file: str = "YT_project.log", level: int = logging.INFO):
    """Налаштовує кореневий логер з файловим та консольним хендлерами.

    Можна викликати багато разів — повторні виклики не дублюють хендлери.
    """
    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        return

    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(formatter)
    root.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(formatter)
    root.addHandler(sh)

    # Додаємо явний атрибут `colors`, який використовується в інших модулях.
    # Деякий код очікує наявність `logger.colors`; за замовчуванням — True
    try:
        setattr(root, "colors", True)
    except Exception:
        pass


def get_logger(name: str):
    """Повертає логер з вказаним іменем (зручний обгортковий хелпер)."""
    return logging.getLogger(name)
