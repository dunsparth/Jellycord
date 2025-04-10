import logging
import os
from datetime import datetime

def init(app_name: str = "app", log_level: str = "INFO") -> None:
    """Initialize logging configuration.
    
    Args:
        app_name: Name of the application for log file naming
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Set up logging format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Convert string log level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Configure logging (console only)
    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        handlers=[
            logging.StreamHandler(),  # Console handler
        ]
    )
    
    # Set discord.py logging to INFO
    logging.getLogger('discord').setLevel(logging.INFO)
    logging.getLogger('discord.http').setLevel(logging.INFO)

# Convenience methods
def debug(msg: str):
    logging.debug(msg)

def info(msg: str):
    logging.info(msg)

def warning(msg: str):
    logging.warning(msg)

def error(msg: str):
    logging.error(msg)

def fatal(msg: str):
    logging.critical(msg)
