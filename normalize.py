import os
import sys
import gzip
import json
import utils
import config
import logging
import pandas as pd
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
  project: dict[str, Ids]

@dataclass
class TaskInfo:
  title: str
  name: str
  version: str

class Normalizer():
  def __init__ (self, project_root: str, log: logging.Logger):
    self.project_root = Path(project_root)
    self.log = log
    self.result_index: pd.DataFrame
    self.id_corrections: pd.DataFrame
    self.project_config: ProjectConfig

    self.current_project_title: Path = None

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
        'Did not find project_config.json in %s. Create the file and fill out'
        ' the structure according to the documentation.',
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

    if any(validated_data_dir.iterdir()):
      self.log.warning(
        '%s is not empty. Clear the directory for a clean run',
        validated_data_dir
      )

  def load_result_index(self, path: Path):
    """Load result index csv file.

    Args:
      path: Path to result index csv.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
      self.log.info(
        'Did not find result_index.csv for project %s, run the download'
        ' script first',
        self.current_project_title
      )
      sys.exit(1)

    self.log.info(
      'Found result_index.csv for project %s',
      self.current_project_title
    )
    self.result_index = pd.read_csv(path)

  def find_id_not_in_project(self) -> bool:
    """Updateda the result index with a new coulumn.

    If a participant ID is not part of the project mark that row as True in the
    new column. The project IDs are specified in project_config.json.

    Returns:
      A boolean value, True if there are IDs that are not part the of the
      project, othervise False.
    """
    self.log.info('Checking if all participant IDs are part of the project')

    project_ids = self.project_config.project[self.current_project_title].ids
    self.result_index["not_in_project_id"] = \
      ~self.result_index["participant_id"].isin(project_ids)

    if self.result_index["not_in_project_id"].any():
      self.log.warning(
        'Found participant ID that is not part of the project, check'
        ' id_corrections.csv'
      )
      return True
    return False

  def find_pid_duplicates(self) -> bool:
    """Find all participants IDs that are on multiple rows with the same study
       title.

    Returns:
      A boolean value, True if there are IDs that are not part the of the
      project, othervise False.
    """
    self.log.info('Checking for duplicate participant IDs')

    duplicates = self.result_index.duplicated(
      keep=False,
      subset=['study_title','participant_id']
    )

    self.result_index["duplicate_id"] = duplicates

    if duplicates.any():
      self.log.warning(
        'Found duplicate participant ID, check id_corrections.csv'
      )
      return True
    return False

  def _filter_result_index(self):
    cond = self.result_index[["not_in_project_id", "duplicate_id"]].any(axis=1)
    self.result_index = self.result_index[cond]

  def validate_pids(self, project_dir: Path):
    """Validate participant IDs by checking for duplicates and comparing all IDs
    to the project participant IDs.

    Args:
      project_dir: The project folder.
    """
    found_id_not_in_project = self.find_id_not_in_project()
    found_pid_duplicates = self.find_pid_duplicates()
    self._filter_result_index()

    path = project_dir / config.VALIDATED_DATA / config.ID_CORRECTIONS

    if path.is_file():
      self.log.info('Found id_corrections.csv')
      id_corrections = pd.read_csv(path)

      # Make a copy of the column 'rule' and then remove it so it is possible to
      # compare if the two DataFrames are equal.
      id_corrections_rule = id_corrections.get(['rule','argument'])
      id_corrections.drop(['rule','argument'],axis=1, inplace=True)

      if not self.result_index.equals(id_corrections):
        self.log.info('Updating id_corrections.csv')
        combined_pd = pd.concat([id_corrections, self.result_index])
        combined_pd.drop_duplicates(inplace=True)
        combined_pd[['rule','argument']] = id_corrections_rule

        combined_pd.to_csv(path, index=False)

      else:
        self.log.info('id_corrections.csv is Up-To-Date')

    elif found_id_not_in_project or found_pid_duplicates:
      self.result_index[['rule','argument']] = None
      self.result_index.to_csv(path, index=False)

      self.log.info(
        'Created %s, in %s validated data, please fill in an action for each'
        ' row. Read the documentation for information about the different'
        ' actions',
        path.name,
        self.current_project_title
      )

    else:
      self.log.info(
        'No duplicate IDs or IDs not in project found in %s',
        self.current_project_title
      )

  def validate_id_corrections(self, project_dir: Path):
    """Check that all entries in id_corrections have a correct action and
      argument.
    """
    path = project_dir / config.VALIDATED_DATA / config.ID_CORRECTIONS

    if not path.is_file():
      return

    self.log.info('Validating id_corrections.csv')
    self.id_corrections = pd.read_csv(path)

    # Check if there are missing rules
    if not self.id_corrections["rule"].notnull().all():
      self.log.critical('Not all rows in id_corrections.csv have a rule')
      sys.exit(1)

    # Check if all rules are correct
    user_rules = set(id_corrections["rule"].unique())
    if not user_rules.issubset(config.rules):
      self.log.critical(
        'Wrong rule applied, check documentation for all rules.'
        ' Rule error: %s',
        user_rules - config.rules
      )
      sys.exit(1)

  def repair_json_data(self, incomplete_json: bytes) -> str:
    """Fix corrupt JSON data by adding missing brackets and data wrapper.

    'incomplete_json' must be an OpenSesame style JSON fragment that ends
    abruptly (typically missing the final ']' and the outer
    '{"data": ..., "context": ...}' wrapper).

    Args:
      incomplete_json: JSON string missing closing brackets and data wrapper.

    Returns:
      Properly structured JSON string with data wrapper.
    """
    incomplete_json_str = incomplete_json.decode()[:-2] + "]"
    fixed_json = '{"data":' + incomplete_json_str + ',"context":{"browser":{}}}'

    return fixed_json

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
      self.log.info('Loading participant raw data data from %s', path.name)
      with gzip.open(path, 'r') as content:
        data = content.read()
        json_content = json.loads(data)
      return json_content

    except gzip.BadGzipFile as e:
      self.log.error('Failed to open zipfile: %s', e)

    except json.JSONDecodeError as e:
      self.log.error('JSON decode error in file: %s: %s', path, e)

      try:
        fixed_content = self.repair_json_data(data)
        json_content = json.loads(fixed_content)
        self.log.info('Error was fixed for file: %s', path)
        return json_content

      except json.JSONDecodeError as e:
        self.log.error('Could not fix corrupt data in file: %s: %s', path, e)

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
      self.log.info('Found the mapping for %s', task_info.title)
      task = self.project_config.task[task_info.name]
      version = task.version[task_info.version]
      return version.mapping

    except KeyError as e:
      self.log.error('Could not find the mapping for %s, make sure to fill out'
      'the project_config.json. %s'
      , task_info.title, e)

  def populate_df(
      self,
      df: pd.DataFrame,
      mapping: dict,
      data: str
  ) -> pd.DataFrame:

    # Opensesame structure
    if isinstance(data, dict):
      self.log.info(
        'Found Openseamse structure in the raw data, collecting variables'
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

  def run(self):
    project_config = self.load_project_config()
    self.project_config = self.validate_project_config(project_config)

    project_dirs = utils.get_all_project_dirs(self.project_root)

    for project_dir in project_dirs:
      self.current_project_title = project_dir.name
      path = project_dir / config.VALIDATED_DATA
      path.mkdir(True, exist_ok=True)

      self.load_result_index(project_dir / config.RESULT_INDEX)
      self.validate_pids(project_dir)
      self.validate_id_corrections(project_dir)

      self._check_validated_data_dir(path)

      path_raw_data = project_dir / config.RAW_DATA

      for file in path_raw_data.glob('*.gz'):
        pid = utils.regex(file.name, config.REGEX_RESULT_PID, group=1)
        rid = utils.regex(file.name, config.REGEX_RESULT_RID, group=1)

        #self.id_corrections[

        data = self.load_participant_raw_data(file)
        task_info = self.get_task_info(data)
        mapping = self.get_mapping(task_info)
        if not mapping:
          continue

        df = utils.create_df_with_headers(mapping)
        df = self.populate_df(df, mapping, data)
        filename = file.name.replace('.txt.gz', '.csv')
        filepath = path / filename
        self.log.info('Saving validated data to %s', filepath.name)
        df.to_csv(filepath, index=False)

    self.log.info('Validation completed')

if __name__ == "__main__":
  load_dotenv()
  project_root = os.getenv('project_root')

  if not project_root:
    print('project_root must be set in .env file')
    exit()

  log = log_util.setupLogging(project_root / config.VALIDATE_LOG)
  log.info('Configuration loaded successfully')

  normalizer = Normalizer(project_root, log)
  normalizer.run()
