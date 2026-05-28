import logging
from pathlib import Path

def setupLogging(filepath: Path):
  filepath.parent.mkdir(parents=True, exist_ok=True)

  logger = logging.getLogger(__file__)
  logger.setLevel(logging.DEBUG)

  console_handler = logging.StreamHandler()
  file_handler = logging.FileHandler(filepath)

  console_handler.setLevel(logging.INFO)
  file_handler.setLevel(logging.DEBUG)

  console_formatter = logging.Formatter("%(levelname)s - %(message)s")
  file_handler_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s"
  )
  console_handler.setFormatter(console_formatter)
  file_handler.setFormatter(file_handler_formatter)

  logger.addHandler(console_handler)
  logger.addHandler(file_handler)

  return logger
