"""BIDSify data downloaded from JATOS."""

# Standard libray
import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

# Third-party
from dotenv import load_dotenv
from tqdm import tqdm

# Local
from utils import ConfigLoader
import config
import log as log_util
import utils

def get_args() -> argparse.Namespace:
  """Parses the command-line arguments.

  Returns: argparse.Namespace: Command-line arguments inputs as an
    argparse.Namespace object.
  """
  parser = argparse.ArgumentParser(
    prog='BIDSify',
    description='BIDSify data from JATOS, validated by the validation script'
  )

  parser.add_argument(
    '-p',
    '--projects',
    nargs='*',
    help='one or more project to BIDSify'
  )

  args = parser.parse_args()

  return args

class BIDSifier():
  """BIDSify downloaded data from JATOS.

  Attributes:
    project_root: Path to where data have been downloaded.
    args: User terminal arguments.
    log: Logger.
  """
  def __init__ (
      self,
      project_root: str,
      args: argparse.Namespace,
      log: logging.Logger
  ):
    self.project_root = Path(project_root)
    self.args         = args
    self.log          = log
    self.configs      = ConfigLoader(project_root / config.TASK_CONFIGS)

  def _make_filenames(self, path: Path, ses: str, sub: str, task: str) -> str:
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

    return data_filename, sidecar_filename

  def run(self):
    """Execute the BIDSify workflow."""
    project_dirs = utils.get_all_project_dirs(self.project_root)
    if not project_dirs:
      self.log.critical(
        'Did not find any project directoris, run the download script first'
      )
      sys.exit(1)

    for project_dir in project_dirs:
      # Skip project if is not specified by the user
      if self.args.projects and project_dir.name not in self.args.projects:
        continue

      path_validated_data = project_dir / config.VALIDATED_DATA

      files = [
        f for f in path_validated_data.glob('*.tsv')
        if f.name != config.VALIDATION_PROTOCOL.name
      ]

      total = len(files)
      if total <= 1:
        self.log.critical(
          'Did not find any result files in %s, run validation.py first',
          project_dir.name / config.VALIDATED_DATA
        )
        continue

      self.log.info(
        'Copying data from %s to %s root and structuring it into BIDS',
        path_validated_data.stem,
        project_dir.name
      )

      pbar = tqdm(
        files,
        total=total,
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

        data_filename, sidecar_filename = self._make_filenames(
                                              path, ses, sub, task
                                            )

        shutil.copyfile(file, path / data_filename)

        try:
          task_config = self.configs.get_config(taskname)
          sidecar = task_config.version[version].metadata
          if sidecar:
            with open(path / sidecar_filename, 'w', encoding="utf-8") as file:
              json.dump(sidecar, file, indent=2)

        except FileNotFoundError:
          self.log.debug('Could not find %s.json', taskname)

        except KeyError:
          self.log.debug(
            'Could not find version %s in %s.json', version, taskname
          )

    self.log.info('BIDSification completed')


def main():
  """Load configuration and start the BIDSifyer."""
  args = get_args()

  load_dotenv()
  project_root = os.getenv('project_root')

  if not project_root:
    print('project_root must be set in .env file')
    sys.exit(1)

  log = log_util.setupLogging(project_root / config.VALIDATE_LOG)
  log.info('Configuration loaded successfully')

  bidsifier = BIDSifier(project_root, args, log)
  bidsifier.run()

if __name__ == "__main__":
  main()
