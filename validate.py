import os
import sys
import utils
import config
import logging
import pandas as pd
import log as log_util
from typing import Any
from pathlib import Path
from dotenv import load_dotenv

class Validator():
  def __init__ (self, project_root: str, log: logging.Logger):
    self.project_root = Path(project_root)
    self.log = log

  def load_project_ids(self) -> dict[str, Any] | None:
    """Load project ids json file.

    Args:
      path: Path to project ids json file.

    Returns:
      A dictonary with list of ids for all projects.
    """
    path = self.project_root / config.PROJECT_IDS
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.is_file():
      self.log.info(
        'Did not find project_ids.json in %s. Create the file and fill it in '
        'according to the documentation if you want the script to '
        'automatically flag IDs that are not part of the project.',
        path
      )
      return None

    self.log.info('Found project_ids.json')

    try:
      with open(path, 'r') as f:
        return json.load(f)
    except json.JSONDecodeError as e:
      self.log.critical('Ivalid JSON in project IDs file: %s', e)
      sys.exit(1)

  def create_df_with_headers(self) -> pd.DataFrame:
    try:
      return pd.DataFrame(columns=config.PROJECT_IDS_HEADERS)
    except Exception as e:
      self.log.error('Could not create DataFrame: %s', e)
      raise

  def run(self):
    project_ids = self.load_project_ids()
    project_dirs = utils.get_all_project_dirs(self.project_root)

    for project_dir in project_dirs:
      path = project_dir / config.NORMALIZED_DATA

      for file in path.glob('*.csv'):
        df = self.create_df_with_headers()
        filepath = project_dir / config.NORMALIZED_DATA/ file.name
        filepath.parent.mkdir(parents=True, exist_ok=True)

    self.log.info('Validation completed')

if __name__ == "__main__":
  load_dotenv()
  project_root = os.getenv('project_root')

  if not project_root:
    print('project_root must be set in .env file')
    exit()

  log = log_util.setupLogging(project_root / config.VALIDATE_LOG)
  log.info('Configuration loaded successfully')

  validator = Validator(project_root, log)
  validator.run()
