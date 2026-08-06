import logging
from pathlib import Path
from tqdm import tqdm


class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            tqdm.write(self.format(record))
        except Exception:
            self.handleError(record)


def setupLogging(filepath: Path):
    filepath.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    console_handler = TqdmLoggingHandler()
    file_handler = logging.FileHandler(filepath)

    console_handler.setLevel(logging.INFO)
    file_handler.setLevel(logging.DEBUG)

    console_handler.setFormatter(
        logging.Formatter("%(levelname)s - %(message)s")
    )

    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
    )

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
