import logging

def setup_logger(name: str = 'quark_client', level: int = logging.INFO):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger

def get_logger(name: str = 'quark_client'):
    return logging.getLogger(name)
