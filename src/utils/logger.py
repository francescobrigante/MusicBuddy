
import logging
import sys

def setup_logger(name="MusicBuddy", level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Check if logger already has handlers to avoid duplicate logs
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger
