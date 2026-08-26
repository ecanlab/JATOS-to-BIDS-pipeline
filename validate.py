"""Validate and process data downloaded from JATOS."""

# Standard library
import argparse
import gzip
import json
import logging
import os
import sys
from pathlib import Path

# Third-party
import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

# Local
from config import BadZipFile
from config import FileError
from config import ValidationError
from config import MissingAction
from config import MissingArgument
from config import NewValidationProtocol
from config import JSONDecodeError
from config import NoTitleFound
from config import NoDataInFile
from config import ProjectConfig
from config import TaskInfo
from config import ValidationProtocolHaveMoreRows
from config import WrongAction
import config
import log as log_util
import utils
from utils import ConfigLoader

def get_args() -> argparse.Namespace:
  """
  Parses the command-line arguments.
  Returns: argparse.Namespace: Command-line arguments inputs as an
    argparse.Namespace object.
  """
  parser = argparse.ArgumentParser(
    prog='validate',
    description='Validate data from JATOS downloaded by the download script'
  )

  parser.add_argument(
    '-p',
    '--projects',
    nargs='*',
    help='one or more project to validate'
  )

  args = parser.parse_args()

  return args

class Validator():
  """Validate and process downloaded data from JATOS.

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
    self.args = args
    self.log = log

    self.configs = ConfigLoader(project_root / config.TASK_CONFIGS)

    self.result_index: pd.DataFrame            | None = None
    self.validation_protocol: pd.DataFrame     | None = None
    self.current_project_config: ProjectConfig | None = None
    self.current_project_title: str            | None = None

    self.tasks_with_no_mapping = set()

  def _check_validated_data_dir(self, validated_data_dir: Path):
    """Check if the validated data directory is empty and inform the user."""
    if len(list(validated_data_dir.iterdir())) > 1:
      self.log.info(
        '%s is not empty, clear the directory for a clean run',
        validated_data_dir.name
      )

  def load_project_config(self, path: Path) -> ProjectConfig | None:
    """Load project config file.

    Args:
      path: Path to result index tsv.

    Returns:
      ProjectConfig
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
      self.log.info(
        'Did not find %s.json in %s, creat it if you want the script to '
        'automatically check if all IDs are part of the project',
        path.name,
        config.PROJECT_CONFIGS
      )
      return None

    self.log.info('Found %s', path.name,)

    with open(path, 'r', encoding="utf-8") as file:
      data = json.load(file)

    return ProjectConfig.model_validate(data)

  def load_result_index(self, path: Path):
    """Load result index tsv file.

    Args:
      path: Path to result index tsv.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
      self.log.info(
        'Did not find result_index.tsv for project %s, run the download '
        'script first',
        self.current_project_title
      )
      sys.exit(1)

    self.log.info(
      'Found %s for project %s',
      config.RESULT_INDEX.name,
      self.current_project_title
    )
    result_index = pd.read_csv(
      path,
      sep='\t',
      dtype={'participant_id': 'string'}
    )
    result_index = result_index.convert_dtypes()
    self.result_index = result_index.reset_index(drop=True)

  def make_validation_protocol(self, project_dir: Path):
    """Creates a validation protocol that is a copy of result index with the
    additonal columns 'action' and 'argument'. In theshe column the user will
    specify what will happen to each result.

    Args:
      project_dir: The project folder.
    """

    path = project_dir / config.VALIDATION_PROTOCOL

    if path.is_file():
      # If there already exist a validation protocol compare it to result index
      # and update it if there are new rows in result index.
      self.log.info('Found %s', config.VALIDATION_PROTOCOL.name)
      self.validation_protocol = pd.read_csv(
        path, sep='\t', dtype={'participant_id':'string'}
      )

      # If result index have fewer rows that validation protocol ask the user to
      # delete the validation protocol so it can be updated with the current
      # result index
      if len(self.result_index) < len(self.validation_protocol):
        raise ValidationProtocolHaveMoreRows(
          'Result index have fewer rows than validation protocol, '
          f'remove {path.name} and run the script again.'
        )

      # Sort both DataFrames by 'start_date' and 'result_id'
      self.validation_protocol.sort_values(
        by=['start_date', 'result_id'],
        ignore_index=True, inplace=True
      )
      self.result_index.sort_values(
        by=['start_date', 'result_id'],
        ignore_index=True, inplace=True
      )

      new_rows = self.result_index.merge(
        self.validation_protocol[['result_uuid']],
        how='left_anti',
        on='result_uuid',
      )

      if not new_rows.empty:
        self.log.info(
          'Adding %d new row(s) to %s',
          len(new_rows),
          config.VALIDATION_PROTOCOL.name
        )

        new_rows['action'] = pd.NA
        new_rows['argument'] = pd.NA

        self.validation_protocol = pd.concat(
          [self.validation_protocol, new_rows]
        )

      self.validate_pids()

      self.validation_protocol.to_csv(path, sep='\t', index=False)

      if new_rows.empty:
        self.log.info('%s is Up-To-Date', config.VALIDATION_PROTOCOL.name)
        return

      try:
        self.validation_protocol.to_csv(path, sep='\t' , index=False)
      except OSError as error:
        self.log.error('Could not save file %s: %s', path, error)

      return

    self.validation_protocol = self.result_index
    self.validation_protocol[[
      'id_not_in_project',
      'duplicate_id',
      'action',
      'argument']] = None

    self.validate_pids()
    self.validation_protocol.to_csv(path, sep='\t', index=False)

    self.log.info(
      'Created %s, in %s, please fill in an action for each '
      'row. Read the documentation for information about the different '
      'actions',
      path.name,
      project_dir.name / config.VALIDATED_DATA
    )
    raise NewValidationProtocol("New validation_protocol.tsv was created")

  def find_id_not_in_project(self):
    """Update validation protocol with information about project membership.

    If a participant ID is not part of the project, mark that row as True.
    The project IDs are specified in project_config.json.
    """
    self.log.info('Checking if all participant IDs are part of the project')

    if not self.current_project_config:
      return

    project_ids = self.current_project_config.IDs

    if not project_ids:
      self.log.info(
        'Did not find IDs for %s in %s, update %s if you want the script '
        'to automatically check if all IDs are part of the project',
        self.current_project_title,
        self.current_project_config.name,
        self.current_project_config.name,
      )
      self.validation_protocol['id_not_in_project'] = pd.NA
      return

    # Save the previous validation to detect changes.
    previous = self.validation_protocol['id_not_in_project'].copy()

    # Allways update 'id_not_in_project' because IDs in 'project_config.json'
    # may change.
    self.validation_protocol['id_not_in_project'] = (
      ~self.validation_protocol['participant_id'].isin(project_ids)
    )

    # Check if this is the first validation of the column
    if previous.isnull().all():
      if self.validation_protocol['id_not_in_project'].any():
        self.log.info(
          'Found participant ID that is not part of the project'
        )
      else:
        self.log.info('No IDs outside of project found')
      return

    # Check if there are newly added rows that have not been validated
    if previous.isnull().any():
      new_rows = previous.isnull()

      if self.validation_protocol.loc[new_rows, 'id_not_in_project'].any():
        self.log.info(
          'New participant ID that is not part of the project found'
        )
        return

    # Check if the project IDs changed the validation result.
    if not previous.equals(self.validation_protocol['id_not_in_project']):
      self.log.info(
        'Project IDs changed, updated participant project validation'
      )
      return

    self.log.info('No new IDs outside of project found')
    return

  def find_pid_duplicates(self):
    """Find all participants IDs that are on multiple rows with the same study
       title.
    """
    self.log.info('Checking for duplicate participant IDs')

    duplicates = self.validation_protocol.duplicated(
      keep=False,
      subset=['study_id','participant_id']
    )

    # Check if all values in 'duplicate_id' are 'None'
    if self.validation_protocol['duplicate_id'].isnull().values.all():
      if duplicates.any():
        self.log.info('Duplicate IDs found')
        self.validation_protocol['duplicate_id'] = duplicates
        return

      self.log.info('No duplicate IDs found')
      self.validation_protocol['duplicate_id'] = duplicates
      return

    # Check if any value in 'duplicate_id' are 'None'
    if self.validation_protocol['duplicate_id'].isnull().values.any():
      new_rows = self.validation_protocol['duplicate_id'].isnull().values.sum()

      if duplicates[-new_rows:].any():
        self.log.info('New duplicate IDs found')
        self.validation_protocol['duplicate_id'] = duplicates
        return

      self.log.info('No new duplicate IDs found')
      self.validation_protocol['duplicate_id'] = duplicates
      return

    # Check if duplicates and 'duplicate_id' are equal
    if self.validation_protocol['duplicate_id'].equals(duplicates):
      return

    self.validation_protocol['duplicate_id'] = duplicates
    self.log.info('Correcting "duplicate_id" column')

  def validate_pids(self):
    """Validate participant IDs by checking for duplicates and comparing all IDs
    to the project participant IDs.
    """
    self.log.info('Validating IDs')
    self.find_id_not_in_project()
    self.find_pid_duplicates()

  def _get_action(self, rid: int) -> config.Action:
    row = self.validation_protocol.loc[
      (self.validation_protocol["result_id"] == rid),
      "action"
    ]

    if row.empty:
      return config.Action.KEEP
    action = row.iloc[0]

    action = config.Action(action)

    return action

  def _get_argument(self, rid: int, pid: int, action: str) -> str:
    argument = self.validation_protocol.loc[
      (self.validation_protocol["result_id"] == rid) &
      (self.validation_protocol["participant_id"] == pid) &
      (self.validation_protocol["action"] == action.value) ,
      "argument"
    ].iloc[0]

    return argument

  def validate_validation_protocol(self):
    """Check that all entries in validation_protocol have a correct action and
      argument.
    """
    self.log.info('Validating %s', config.VALIDATION_PROTOCOL.name)

    # Check if there are missing actions
    if not self.validation_protocol["action"].notnull().all():
      raise MissingAction(
        f'Not all rows in {config.VALIDATION_PROTOCOL.name} have a action',
      )

    # Check if all actions are correct
    user_actions = set(self.validation_protocol["action"].unique())
    if not user_actions.issubset(config.actions):
      raise WrongAction(
        f'Wrong action applied, check documentation for all actions. '
        f'Action error: {user_actions - config.actions}'
      )

    # Check that all actions that requiers an argument has one
    arguments = self.validation_protocol.loc[
      (self.validation_protocol["action"] == config.Action.REASSIGN_ID.value) ,
      "argument"
    ]
    if  arguments.isna().any():
      raise MissingArgument(
        'Missing argument for reassign_id, check'
        f'{config.VALIDATION_PROTOCOL.name}'
      )

  @staticmethod
  def repair_json_data(incomplete_json: bytes, pos: int) -> str:
    """Fix corrupt JSON data by adding missing brackets and data wrapper.

    'incomplete_json' must be an OpenSesame style JSON fragment that ends
    abruptly (typically missing the final ']' and the outer
    '{"data": ..., "context": ...}' wrapper).

    Args:
      incomplete_json: JSON string missing closing brackets and data wrapper.
      pos: The position from the end of the JSON where the ']' will be placed.

    Returns:
      Properly structured JSON string with data wrapper.
    """
    incomplete_json_str = incomplete_json.decode()[:-pos] + "]"
    fixed_json = '{"data":' + incomplete_json_str + ',"context":{"browser":{}}}'
    json_content = json.loads(fixed_json)

    return json_content

  def load_participant_raw_data(self, path: Path) -> dict | None:
    """Load participant raw data

    Args:
      path: Path to a participant raw data in a gz file.

    Side effect:
      Reads file from disk.

    Returns:
      Participant raw data as dict.
    """
    try:
      self.log.debug('Loading participant raw data data from %s', path.name)
      with gzip.open(path, 'r') as content:
        data = content.read()
        if len(data) == 1:
          raise NoDataInFile(f'File {path.name} dose not contain any data')

        json_content = json.loads(data)
      return json_content

    except gzip.BadGzipFile as error:
      raise BadZipFile('Failed to open zipfile: ') from error

    except json.JSONDecodeError as error:
      self.log.debug('JSON decode error in file: %s: %s', path.name, error)

      try:
        json_content = self.repair_json_data(data, 2)
        self.log.debug('Error was fixed for file: %s', path.name)
        return json_content

      except json.JSONDecodeError:
        try:
          json_content = self.repair_json_data(data, 1)
          self.log.debug('Error was fixed for file: %s', path.name)
          return json_content

        except json.JSONDecodeError as json_error:
          raise JSONDecodeError(
            f'Could not fix corrupt data in file {path.name}'
          ) from json_error

    return None

  @staticmethod
  def _get_task_title(data: str) -> str:
    task_title: str | None = None

    try:
      # Opensesame structure
      if isinstance(data, dict):
        task_title = data["data"][0]["title"]
        return task_title

      # jsPsych
      if isinstance(data, list):
        # In jsPsych we don't know where the title is stored so we need to go
        # trough all trials until we find the title
        for trial in data:
          # The title key is user defined
          for title in config.TITLE_KEYS:
            task_title = trial.get(title)
            if task_title is not None:
              return task_title
          raise NoTitleFound('No title found')

      raise NoTitleFound('No title found')

    except IndexError as error:
      raise NoDataInFile('No data found: ') from error

  def _get_task_info(self, data: str) -> TaskInfo:
    title = self._get_task_title(data)
    name = utils.regex(title, config.REGEX_TASK_NAME)
    version = utils.regex(title, config.REGEX_TASK_VERSION)

    return TaskInfo(title=title, name=name.strip(), version=version)

  def _load_mapping(self, task_info: TaskInfo) -> dict | None:
    try:
      task_config = self.configs.get_config(task_info.name)
      mapping = task_config.version[task_info.version].mapping
      self.log.debug('Found %s.json', task_info.name)
      self.log.debug('Validating %s.json', task_info.name)

    except json.JSONDecodeError as error:
      self.log.warning('Invalid JSON in project config: %s', error)
      return None

    except ValidationError as error:
      self.log.warning('Could not validate JSON structure: %s', error)
      return None

    except FileNotFoundError as error:
      self.log.error(
        'Did not find %s.json in %s', task_info.name, config.TASK_CONFIGS
      )
      self.tasks_with_no_mapping.add(task_info.name)
      return None

    except KeyError:
      self.log.debug(
        'Could not find mapping for version %s in %s.json',
        task_info.version, task_info.name
      )
      return None

    return mapping

  def populate_result(
      self,
      result: pd.DataFrame,
      mapping: dict,
      data: str
  ) -> pd.DataFrame:
    """Identifies the structure of the data and goes trough each trial and
      populate the result dataframe with values based on the mapping keys.

    Args:
      result: Dataframe that will be populated the values based on the mapping
        keys.
      mapping: Mapping with the tasks specific keys.
      data: The data contaning all trials.

    Returns:
      Result dataframe.
      """
    # Opensesame structure
    if isinstance(data, dict):
      self.log.debug(
        'Found Opensesame structure in the raw data, collecting variables'
      )
      for trial in data['data']:
        result.loc[len(result)] = [trial.get(k, None) for k in mapping.values()]

    # jsPsych structure
    if isinstance(data, list):
      self.log.debug(
        'Found jsPsych structure in the raw data, collecting variables'
      )
      for trial in data:
        result.loc[len(result)] = [trial.get(k, None) for k in mapping.values()]

    return result

  def _new_filename(self, filename: str, regex: str, new_part: str) -> str:
    match = utils.regex(filename, regex, group=None)
    start = filename[:match.start()]
    end   = filename[match.end():]
    prefix = utils.regex(regex, config.REGEX_PREFIX)
    filename = start  + prefix + new_part + end

    return filename

  def _process_project_files(self, project_dir, path):
    """Process all raw data files in a project."""
    path_raw_data = project_dir / config.RAW_DATA

    files = list(path_raw_data.glob('*.gz'))
    pbar = tqdm(
      files,
      total=len(files),
      desc=f'Processing {project_dir.name}: ',
      unit=' files'
    )

    for file in pbar:
      pbar.set_postfix(file=file.name)
      rid = int(utils.regex(file.name, config.REGEX_RID, group=1))
      sub = utils.regex(file.name, config.REGEX_SUB, group=1)

      action = self._get_action(rid)

      if action == config.Action.EXCLUDE:
        self.log.debug('Excluding %s', file.name)
        continue

      try:
        data = self.load_participant_raw_data(file)
      except FileError as error:
        self.log.debug(f'Error loading file: {error}')
        continue

      try:
        task_info = self._get_task_info(data)

      except FileError as error:
        self.log.debug(f'Error loading file {file.name}: {error}')
        continue

      except NoTitleFound:
        self.log.critical(
          'Could not find title in %s data add title key in config',
          file.name
        )
        continue

      if task_info.name in self.tasks_with_no_mapping:
        continue

      mapping = self._load_mapping(task_info)
      if not mapping:
        continue

      result = utils.create_df_with_headers(mapping)
      result = self.populate_result(result, mapping, data)
      filename = file.name
      filename = filename.replace('.txt.gz', '')
      filename += f'_taskname-{task_info.name}'
      filename += f'_{task_info.version}.tsv'

      if action == config.Action.REASSIGN_ID:
        new_pid = str((self._get_argument(rid, sub, action)))
        filename = self._new_filename(filename, config.REGEX_SUB, new_pid)

      filepath = path / filename

      self.log.debug('Saving validated data to %s', filepath.name)
      result.to_csv(filepath, sep='\t', index=False)

  def run(self):
    """Execute the validate workflow."""
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
      self.log.info('-- %s --', project_dir.name)

      self.current_project_title = project_dir.name
      self.current_project_config = self.load_project_config(
        self.project_root /
        config.PROJECT_CONFIGS /
        project_dir.with_suffix('.json').name
      )
      path = project_dir / config.VALIDATED_DATA
      path.mkdir(True, exist_ok=True)

      self.load_result_index(project_dir / config.RESULT_INDEX)

      try:
        self.make_validation_protocol(project_dir)
        self.validate_validation_protocol()

      except ValidationError as error:
        self.log.info('Skipping %s: %s', project_dir.name, error)
        continue

      self._check_validated_data_dir(path)
      self._process_project_files(project_dir, path)
      self.current_project_config = None

    self.log.info('Validation completed')

def main():
  """Load configuration and start the validator."""
  args = get_args()

  load_dotenv()
  project_root = os.getenv('PROJECT_ROOT')

  if not project_root:
    print('project_root must be set in .env file')
    sys.exit(1)

  log = log_util.setupLogging(project_root / config.VALIDATE_LOG)
  log.info('Configuration loaded successfully')

  validator = Validator(project_root, args, log)
  validator.run()

if __name__ == "__main__":
  main()
