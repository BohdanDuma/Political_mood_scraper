import logging


def configure_logging(log_file: str = "YT_project.log", level: int = logging.INFO):
    """Configure a centralized root logger with file+stream handlers.

    Safe to call multiple times; subsequent calls are no-ops if handlers exist.
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

    # provide an explicit attribute for colorized logging flags used elsewhere
    # some code expects `logger.colors` to exist; default to True
    try:
        setattr(root, "colors", True)
    except Exception:
        pass


def get_logger(name: str):
    return logging.getLogger(name)
