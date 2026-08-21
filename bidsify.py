# Standard libray
import logging
import os
import shutil
from pathlib import Path

# Third-party
from dotenv import load_dotenv
from tqdm import tqdm

# Local
import config
import log as log_util
import utils

class BIDSifier():
  def __init__ (self, project_root: str, log: logging.Logger):
    self.project_root = Path(project_root)
    self.log = log

  def run(self):
    project_dirs = utils.get_all_project_dirs(self.project_root)
    if not project_dirs:
      self.log.critical(
        'Did not find any project directoris, run the download script first'
      )
      sys.exit(1)

    for project_dir in project_dirs:

      path_validated_data = project_dir / config.VALIDATED_DATA

      self.log.info(
        'Copying data from %s to %s root and structuring it into BIDS',
        path_validated_data.stem,
        project_dir.name
      )

      files = [
        f for f in path_validated_data.glob('*.tsv')
        if f.name != 'id_corrections.tsv'
      ]

      pbar = tqdm(
        files,
        total=len(files),
        desc=f'BIDSifying {project_dir.name}: ',
        unit=' files'
      )

      for file in pbar:
        sub = utils.regex(file.name, config.REGEX_SUB)
        ses = utils.regex(file.name, config.REGEX_PROJECT_SES)
        task = utils.regex(file.name, config.REGEX_PROJECT_TASK)

        path = project_dir / sub

        if ses:
          path /= ses

        path /= 'beh'
        path.mkdir(parents=True, exist_ok=True)

        filename = f'{sub}_'
        if ses:
          filename += f'{ses}_'

        filename += f'{task}_beh.tsv'
        shutil.copyfile(file, path / filename)

    self.log.info('BIDSification completed')

if __name__ == "__main__":
  load_dotenv()
  project_root = os.getenv('project_root')

  if not project_root:
    print('project_root must be set in .env file')
    exit()

  log = log_util.setupLogging(project_root / config.VALIDATE_LOG)
  log.info('Configuration loaded successfully')

  bidsifier = BIDSifier(project_root, log)
  bidsifier.run()
