"""Utility functions for the main scripts.."""

# Standard library
import datetime
import json
import re
from pathlib import Path

# Third-party
import pandas as pd

# Local
import config
from config import TaskConfig


class ConfigLoader:
  """Loads projects config files and validates the structure."""
  def __init__(self, path: Path):
    self.path = path
    self._configs = {}

  def get_config(self, name: str) -> TaskConfig:
    """Get project config file, if it is not allready loaded, load it.

    Args:
      name: Name of the project.

    Return:
      A TaskConfig.
    """
    if not name in self._configs:
      self._configs[name] = self._load_config(name)

    return self._configs[name]

  def _load_config(self, name: str) -> TaskConfig:
    path = self.path / f'{name}.json'

    with open(path, 'r', encoding="utf-8") as file:
      data = json.load(file)

    return self._validate_data(data)

  def _validate_data(self, data: TaskConfig) -> TaskConfig:
    return TaskConfig.model_validate(data)

def create_df_with_headers(headers: dict | list) -> pd.DataFrame:
  """Creates a dataframe and populate the columns with titles.

  Args:
    headers: Either a dict where the keys are the headers or a list with
    headers.

  Returns:
    A pandas dataframe with column titles.
  """
  columns = None
  if isinstance(headers, dict):
    columns = list(headers.keys())
  if isinstance(headers, list):
    columns = headers
  return pd.DataFrame(columns=columns)

def get_all_project_dirs(project_root: Path) -> list[Path]:
  """Get all directories in root that have soursdata/JATOS directories.

  Excludes all project that dose not have any data from JATOS.

  Args:
    project_root: The project root directory.

  Returns:
    A list with all project directories.
  """
  dirs = []
  for directory in project_root.iterdir():
    if Path(directory / config.SOURCE_JATOS).is_dir():
      dirs.append(directory)
  return dirs

def regex(text: str, regex_str: str, group: int | None = 0) -> str:
  """Get the matching regex from a string.

  PRE:
    regex_str should be a raw string, r''

  ARGS:
    text: The string that will be searched.
    regex: Raw string regex pattern to match against the text.
    group: Specify a subgroups of the match or None to return the whole result.

  RETURNS:
    The matching string or an empty string if nothing was found.
  """
  result = re.search(regex_str, text)

  if not result:
    return ''

  if group is None:
    return result

  return result.group(group)

def convert_to_local_tz(date_ms: float) -> str:
  """Convert an float to local timezone with the format (YYYY-MM-DD HH-mm-ss)
  Pre:
    date must be a date reprecented as miliseconds.

  Args:
    date_ms (float): A date reprecented as miliseconds.

  Returns:
    str: The time with the format (YYYY-MM-DD HH-mm-ss) converted to the local
    timezone.
  """
  # Convert the date in ms to UTC format
  start_date_utc = datetime.datetime.fromtimestamp(
    date_ms / 1000.0,
    tz=datetime.timezone.utc
  )
  # Convert to local time
  date_local_tz = start_date_utc.astimezone(config.LOCAL_TZ)

  # Apply format
  formatted_date = date_local_tz.strftime(config.TIME_FORMAT)

  return formatted_date
