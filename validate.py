import os
import sys
import gzip
import json
import utils
import config
import logging
import pandas as pd
from tqdm import tqdm
import log as log_util
from typing import Any
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass
from pydantic import BaseModel, ValidationError

class Version(BaseModel):
  mapping: dict[str, str]

class Task(BaseModel):
  version: dict[str, Version]

class Ids(BaseModel):
  ids: list[int]

class Project(BaseModel):
  title: dict[Ids, str]

class ProjectConfig(BaseModel):
  task: dict[str, Task]
  project: dict[str, Ids] | None = None

@dataclass
class TaskInfo:
  title: str
  name: str
  version: str

class ValidationError(Exception):
  """Base class for validation errors."""
  pass

class NewIdCorrectionsFile(ValidationError):
  """Raised when a new validation_protocol.tsv is created in a project."""
  pass

class MissingAction(ValidationError):
  """Raised when a action is missing for a line in the validation_protocol.tsv.
  """
  pass

class MissingArgument(ValidationError):
  """Raised when an Argument is missing for a action in validation_protocol.tsv.
  """
  pass

class WrongAction(ValidationError):
  """Raised when a wrong action is specified in validation_protocol.tsv."""
  pass

class FileError(Exception):
  """Base class for file error."""

class BadZipFile(FileError):
  """Raised when a zipfile cannot be opend."""
  pass

class JSONDecodeError(FileError):
  """Raised when JSON structure cannot be loaded."""
  pass

class NoDataInFile(FileError):
  """Raised when there is only one symbol in data."""

class Validator():
  def __init__ (self, project_root: str, log: logging.Logger):
    self.project_root = Path(project_root)
    self.log = log
    self.result_index: pd.DataFrame
    self.validation_protocol: pd.DataFrame
    self.project_config: ProjectConfig

    self.current_project_title: Path = None

    self.tasks_with_no_mapping = set()

  def load_project_config(self) -> dict[str, Any]:
    """Load project config json file.

    Args:
      path: Path to project config json file.

    Returns:
      A dictonary with the content from the json file.
    """
    path = self.project_root / config.PROJECT_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.is_file():
      self.log.critical(
        'Did not find project_config.json in %s. Create the file and fill out '
        'the structure according to the documentation.',
        path
      )
      sys.exit(1)

    self.log.info('Found project_config.json')

    try:
      with open(path, 'r') as f:
        return json.load(f)
    except json.JSONDecodeError as e:
      self.log.critical('Ivalid JSON in project config: %s', e)
      sys.exit(1)

  def validate_project_config(self, project_config: dict) -> ProjectConfig:
    try:
      self.log.info('Validating project config')
      return ProjectConfig.model_validate(project_config)

    except ValidationError as e:
      self.log.critical('Could not validate json structure: %s', e)
      sys.exit(1)

  def _check_validated_data_dir(self, validated_data_dir: Path):
    """Check if the validated data directory is empty and inform the user."""
    if len(list(validated_data_dir.iterdir())) > 1:
      self.log.info(
        '%s is not emty, clear the directory for a clean run',
        validated_data_dir.name
      )

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
    result_index = pd.read_csv(path, sep='\t', dtype={'participant_id': 'string'})
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

      # Sort both DataFrames by 'start_date' and 'result_id'
      self.validation_protocol.sort_values(
        by=['start_date', 'result_id'],
        ignore_index=True, inplace=True
      )
      self.result_index.sort_values(
        by=['start_date', 'result_id'],
        ignore_index=True, inplace=True
      )

      protocol_compare = self.validation_protocol.drop(['action','argument'],axis=1)

      left = self.result_index.merge(
          self.validation_protocol,
          how='left',
          indicator=True
        )
      new_rows = left[(left._merge=='left_only')].drop('_merge', axis=1)

      if new_rows.empty:
        self.log.info('%s is Up-To-Date', config.VALIDATION_PROTOCOL.name)
        self.validate_pids()
        return

      else:
        self.log.info(
          'Adding %d new row(s) to %s',
          len(new_rows),
          config.VALIDATION_PROTOCOL.name
        )

        new_rows['action'] = pd.NA
        new_rows['argument'] = pd.NA

        self.validation_protocol = pd.concat([self.validation_protocol, new_rows])
        self.validate_pids()
        self.validation_protocol.to_csv(path, sep='\t' , index=False)
        return

    else:
      self.validation_protocol = self.result_index
      self.validation_protocol[[
        'id_not_in_project',
        'duplicate_id',
        'action',
        'argument']] = None

      self.validate_pids()

      self.validation_protocol.to_csv(path, sep='\t', index=False)

      self.log.info(
        'Created %s, in %s validated data, please fill in an action for each '
        'row. Read the documentation for information about the different '
        'actions',
        path.name,
        self.current_project_title
      )
      raise NewIdCorrectionsFile("New validation_protocol.tsv was created")

  def find_id_not_in_project(self) -> bool:
    """Updatedas validation protocol with information if the participant ID is
    part of the project or not.

    If a participant ID is not part of the project mark that row as True in the
    new column. The project IDs are specified in project_config.json.
    """
    self.log.info('Checking if all participant IDs are part of the project')
    try:
      project = self.project_config.project.get(self.current_project_title)
      project_ids = project.get(ids)
    except Exception:
      self.log.error(
        'Did not find IDs for %s in %s, update %s if you want the script to '
        'automatically check if all IDs are part of the project',
        self.current_project_title,
        config.PROJECT_CONFIG.name,
        config.PROJECT_CONFIG.name
      )
      self.validation_protocol['id_not_in_project'] = False
      return

    # Check if all values in 'id_not_in_project' are 'None'
    if self.calidation_protocol['id_not_in_project'].isnull().values().all():
      self.validation_protocol['id_not_in_project'] = \
        ~self.validation_protocol['id_not_in_project'].isin(project_ids)

      if self.validation_protocol['id_not_in_project'].any():
        self.log.warning('Found participant ID that is not part of the project')
        return

    # Check if any value in 'id_not_in_project' are 'None'
    if self.validation_protocol['id_not_in_project'].isnull().values.any():
      if duplicates.any():
        self.log.info(
          'New participant ID that is not part of the project found'
        )
        self.validation_protocol['id_not_in_project'] = duplicates
        return
      else:
        self.log.info('No new duplicate IDs found')
        return

    return

  def find_pid_duplicates(self) -> bool:
    """Find all participants IDs that are on multiple rows with the same study
       title.
    """
    self.log.info('Checking for duplicate participant IDs')

    duplicates = self.validation_protocol.duplicated(
      keep=False,
      subset=['study_title','participant_id']
    )

    # Check if all values in 'duplicate_id' are 'None'
    if self.validation_protocol['duplicate_id'].isnull().values.all():
      if duplicates.any():
        self.log.info('Duplicate IDs found')
        self.validation_protocol['duplicate_id'] = duplicates
        return
      else:
        self.log.info('No duplicate IDs found')
        return

    # Check if any value in 'duplicate_id' are 'None'
    if self.validation_protocol['duplicate_id'].isnull().values.any():
      new_rows = self.validation_protocol['duplicate_id'].isnull().values.sum()
      if duplicates[:-new_rows].any():
        self.log.info('New duplicate IDs found')
        self.validation_protocol['duplicate_id'] = duplicates
        return
      else:
        self.log.info('No new duplicate IDs found')
        return

    # Check if duplicates and 'duplicate_id' are equal
    if self.validation_protocol['duplicate_id'].equals(duplicates):
      return

    else:
      self.validation_protocol['duplicate_id'] = duplicates
      self.log.info('Correcting "duplicate_id" column')

  def validate_pids(self):
    """Validate participant IDs by checking for duplicates and comparing all IDs
    to the project participant IDs.
    """
    self.log.info('Validating IDs')
    found_id_not_in_project = self.find_id_not_in_project()
    found_pid_duplicates = self.find_pid_duplicates()

  def _get_action(self, rid: int, pid: int) -> config.Action:
    row = self.validation_protocol.loc[
      (self.validation_protocol["result_id"] == rid) &
      (self.validation_protocol["participant_id"] == pid),
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

  def validate_validation_protocol(self, project_dir: Path):
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

  def repair_json_data(self, incomplete_json: bytes, pos: int) -> str:
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

    except gzip.BadGzipFile as e:
      raise BadZipFile(f'Failed to open zipfile: {e}')

    except json.JSONDecodeError as e:
      self.log.debug('JSON decode error in file: %s: %s', path.name, e)

      try:
        json_content = self.repair_json_data(data, 2)
        self.log.info('Error was fixed for file: %s', path.name)
        return json_content

      except json.JSONDecodeError as e:
        try:
          json_content = self.repair_json_data(data, 1)
          self.log.debug('Error was fixed for file: %s', path.name)
          return json_content

        except json.JSONDecodeError as e:
          raise JSONDecodeError(
            f'Could not fix corrupt data in file {path.name}, {e}'
          )

    return None

  def get_task_title(self, data: str) -> str:
    task_title: str

    # Opensesame structure
    if isinstance(data, dict):
      task_title = data["data"][0]["title"]

    # jsPsych
    if isinstance(data, list):
        task_title = None
        for trial in data:
            task_title = trial.get("title")
            if task_title:
                break

    return task_title

  def get_task_info(self, data: str) -> TaskInfo:
    title = self.get_task_title(data)
    name = utils.regex(title, config.REGEX_TASK_NAME)
    version = utils.regex(title, config.REGEX_TASK_VERSION)

    return TaskInfo(title=title, name=name.strip(), version=version)

  def get_mapping(self, task_info: TaskInfo) -> dict:
    try:
      self.log.info('Loading mapping for %s', task_info.title)
      task = self.project_config.task[task_info.name]
      version = task.version[task_info.version]
      return version.mapping

    except KeyError as e:
      self.tasks_with_no_mapping.add(task_info.title)
      self.log.error('Could not find mapping for %s, make sure to fill out '
      'the project_config.json. %s'
      , task_info.title, e)
      self.log.info('Looking trough the rest of the files for other versions')

  def populate_df(
      self,
      df: pd.DataFrame,
      mapping: dict,
      data: str
  ) -> pd.DataFrame:

    # Opensesame structure
    if isinstance(data, dict):
      self.log.info(
        'Found Opensesame structure in the raw data, collecting variables'
      )
      for trial in data['data']:
        df.loc[len(df)] = [trial.get(k, None) for k in mapping.values()]

    # jsPsych structure
    if isinstance(data, list):
      self.log.info(
        'Found jsPsych structure in the raw data, collecting variables'
      )
      for trial in data:
        df.loc[len(df)] = [trial.get(k, None) for k in mapping.values()]

    return df

  def _new_filename(self, rid: int, pid: int, action: str, filename: str) -> str:
    new_pid = str(int(self._get_argument(rid, pid, action)))
    match = utils.regex(filename, config.REGEX_SUB, group=None)
    start = filename[:match.start()]
    end   = filename[match.end():]
    filename = start  + 'sub-' + new_pid + end

    return filename

  def run(self):
    project_config = self.load_project_config()
    self.project_config = self.validate_project_config(project_config)

    project_dirs = utils.get_all_project_dirs(self.project_root)
    if not project_dirs:
      self.log.critical(
        'Did not find any project directoris, run the download script first'
      )
      sys.exit(1)

    for project_dir in project_dirs:
      self.log.info('-- %s --', project_dir.name)

      self.current_project_title = project_dir.name
      path = project_dir / config.VALIDATED_DATA
      path.mkdir(True, exist_ok=True)

      self.load_result_index(project_dir / config.RESULT_INDEX)

      try:
        self.make_validation_protocol(project_dir)
        self.validate_validation_protocol(project_dir)

      except ValidationError as e:
        self.log.info('Skipping %s: %s', project_dir.name, e)
        continue

      self._check_validated_data_dir(path)

      path_raw_data = project_dir / config.RAW_DATA

      files = list(path_raw_data.glob('*.gz'))
      for file in tqdm(files, total=len(files)):
        rid = int(utils.regex(file.name, config.REGEX_RESULT_RID, group=1))
        sub = utils.regex(file.name, config.REGEX_SUB, group=1)

        action = self._get_action(rid, sub)

        if action == config.Action.EXCLUDE:
          self.log.debug('Excluding %s', file.name)
          continue

        try:
          data = self.load_participant_raw_data(file)
        except FileError as e:
          self.log.debug(f'Error loading file: {e}')

        task_info = self.get_task_info(data)

        if task_info.title in self.tasks_with_no_mapping:
          continue

        mapping = self.get_mapping(task_info)
        if not mapping:
          continue

        df = utils.create_df_with_headers(mapping)
        df = self.populate_df(df, mapping, data)
        filename = file.name.replace('.txt.gz', '.tsv')

        if action == config.Action.REASSIGN_ID:
          filename = self._new_filename(rid, sub, action, filename)

        filepath = path / filename
        self.log.debug('Saving validated data to %s', filepath.name)
        df.to_csv(filepath, sep='\t', index=False)

    self.log.info('Validation completed')

if __name__ == "__main__":
  load_dotenv()
  project_root = os.getenv('PROJECT_ROOT')

  if not project_root:
    print('project_root must be set in .env file')
    exit()

  log = log_util.setupLogging(project_root / config.VALIDATE_LOG)
  log.info('Configuration loaded successfully')

  validator = Validator(project_root, log)
  validator.run()
