import logging
import sys
import os

def setup_logger(name: str = "contai_pro") -> logging.Logger:
    """
    Configures and returns a centralized logger for the application.
    Outputs to stdout (Docker compatible) with timestamps and log levels.
    """
    logger = logging.getLogger(name)
    
    # Only configure if we haven't already (prevents duplicate handlers)
    if not logger.handlers:
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        
        # Validating log level fallback
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if log_level not in valid_levels:
            log_level = "INFO"
            
        logger.setLevel(getattr(logging, log_level))

        # Create stdout handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, log_level))

        # Create formatter
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
        
    return logger

# Global logger instance to be imported across the app
logger = setup_logger()
