# Standard libray
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

# Third-party
from dotenv import load_dotenv
from tqdm import tqdm

# Local
from config import NoProjectConfig
from utils import ConfigLoader
import config
import log as log_util
import utils

class BIDSifier():
  def __init__ (self, project_root: str, log: logging.Logger):
    self.project_root = Path(project_root)
    self.log = log
    self.configs = ConfigLoader(project_root / config.TASK_CONFIGS)

  def run(self):
    project_dirs = utils.get_all_project_dirs(self.project_root)
    if not project_dirs:
      self.log.critical(
        'Did not find any project directoris, run the download script first'
      )
      sys.exit(1)

    for project_dir in project_dirs:

      path_task_config = (
        self.project_root /
        config.CODE_JATOS /
        Path(project_dir.name + '.json')
      )

      path_validated_data = project_dir / config.VALIDATED_DATA

      self.log.info(
        'Copying data from %s to %s root and structuring it into BIDS',
        path_validated_data.stem,
        project_dir.name
      )

      files = [
        f for f in path_validated_data.glob('*.tsv')
        if f.name != config.VALIDATION_PROTOCOL.name
      ]

      pbar = tqdm(
        files,
        total=len(files),
        desc=f'BIDSifying {project_dir.name}: ',
        unit=' files'
      )

      for file in pbar:
        sub      = utils.regex(file.name, config.REGEX_SUB)
        ses      = utils.regex(file.name, config.REGEX_SES)
        task     = utils.regex(file.name, config.REGEX_TASK, 1)
        taskname = utils.regex(file.name, config.REGEX_TASKNAME, 1)
        version  = utils.regex(file.name, config.REGEX_VERSION, 1)

        path = project_dir / sub

        if ses:
          path /= ses

        path /= 'beh'
        path.mkdir(parents=True, exist_ok=True)

        filename = f'{sub}_'

        if ses:
          filename += f'{ses}_'

        filename += f'{task}_beh'

        data_filename = filename + '.tsv'
        sidecar_filename = filename + '.json'

        shutil.copyfile(file, path / data_filename)

        try:
          task_config = self.configs.get_config(taskname)
          sidecar = task_config.version[version].metadata
          if sidecar:
            with open(path / sidecar_filename, 'w') as file:
              json.dump(sidecar, file, indent=2)

        except FileNotFoundError:
          self.log.debug('Could not find %s.json', taskname)

        except KeyError:
          self.log.debug(
            'Could not find version %s in %s.json', version, taskname
          )

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
