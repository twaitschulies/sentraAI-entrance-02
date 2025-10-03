import os
import logging
from logging.handlers import RotatingFileHandler
from app.config import LOG_DIR, LOG_FILE

def setup_logging(app):
    os.makedirs(LOG_DIR, exist_ok=True)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2*1024*1024, backupCount=3)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
    app.logger.addHandler(file_handler)
