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

class SchemaMap(BaseModel):
  task: dict[str, Task]

@dataclass
class TaskInfo:
  title: str
  name: str
  version: str

class Normalizer():
  def __init__ (self, project_root: str, log: logging.Logger):
    self.project_root = Path(project_root)
    self.log = log
    self.schema_map: SchemaMap

  def load_schema_map(self) -> dict[str, Any]:
    """Load schema map json file.

    Args:
      path: Path to schema map json file.

    Returns:
      A dictonary with the content from the json file.
    """
    path = self.project_root / config.SCHEMA_MAP
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.is_file():
      self.log.critical(
        'Did not find schema_map.json in %s. Create the file and fill out the '
        'structure according to the documentation.',
        path
      )
      sys.exit(1)

    self.log.info('Found schema_map.json')

    try:
      with open(path, 'r') as f:
        return json.load(f)
    except json.JSONDecodeError as e:
      self.log.critical('Ivalid JSON in schema map: %s', e)
      sys.exit(1)

  def validate_schema_map(self, schema_map_data: dict) -> SchemaMap:
    try:
      self.log.info('Validating schema map')
      return SchemaMap.model_validate(schema_map_data)

    except ValidationError as e:
      self.log.critical('Could not validate json structure: %s', e)
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
    name = utils.get_part_of_string(title, config.REGEX_TASK_NAME)
    version = utils.get_part_of_string(title, config.REGEX_TASK_VERSION)

    return TaskInfo(title=title, name=name.strip(), version=version)

  def get_mapping(self, task_info: TaskInfo) -> dict:
    try:
      self.log.info('Found the mapping for %s', task_info.title)
      task = self.schema_map.task[task_info.name]
      version = task.version[task_info.version]
      return version.mapping

    except KeyError as e:
      self.log.error('Could not find the mapping for %s, make sure to fill out'
      'the schema_map.json. %s'
      , task_info.title, e)
      raise

  def create_df_with_headers(self, mapping: dict) -> pd.DataFrame:
    try:
      columns = list(mapping.keys())
      return pd.DataFrame(columns=columns)
    except Exception as e:
      self.log.error('Could not create DataFrame from mapping: %s', e)
      raise

  def populate_df(
      self,
      df: pd.DataFrame,
      mapping: dict,
      data: str
  ) -> pd.DataFrame:

    # Opensesame structure
    if isinstance(data, dict):
      self.log.info(
        'Found Openseamse structure in the raw data, collectiong variables'
      )
      for trial in data['data']:
        df.loc[len(df)] = [trial.get(k, None) for k in mapping.values()]

    # jsPsych structure
    if isinstance(data, list):
      self.log.info(
        'Found jsPsych structure in the raw data, collectiong variables'
      )
      for trial in data:
        df.loc[len(df)] = [trial.get(k, None) for k in mapping.values()]

    return df

  def run(self):
    schema_map_data = self.load_schema_map()
    self.schema_map = self.validate_schema_map(schema_map_data)
    project_dirs = utils.get_all_project_dirs(self.project_root)

    for project_dir in project_dirs:
      path = project_dir / config.RAW_DATA

      for file in path.glob('*.gz'):
        data = self.load_participant_raw_data(file)
        task_info = self.get_task_info(data)
        mapping = self.get_mapping(task_info)
        if not mapping:
          continue

        df = self.create_df_with_headers(mapping)
        df = self.populate_df(df, mapping, data)
        filename = file.name.replace('.txt.gz', '.csv')
        filepath = project_dir / config.NORMALIZED_DATA/ filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        self.log.info('Saving normalized data to %s', filepath.name)
        df.to_csv(filepath, index=False)

    self.log.info('Normalization completed')

if __name__ == "__main__":
  load_dotenv()
  project_root = os.getenv('project_root')

  if not project_root:
    print('project_root must be set in .env file')
    exit()

  log = log_util.setupLogging(project_root / config.NORMALIZE_LOG)
  log.info('Configuration loaded successfully')

  normalizer = Normalizer(project_root, log)
  normalizer.run()
