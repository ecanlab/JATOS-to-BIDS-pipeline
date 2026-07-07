import re
import config
import datetime
import pandas as pd
from pathlib import Path

def create_df_with_headers(headers: dict | list) -> pd.DataFrame:
  """Creates a dataframe and populate the columns with titles.

  Args:
    headers: Either a dict where the keys are the headers or a list with
    headers.

  Returns:
    A pandas dataframe with column titles.
  """
  try:
    if isinstance(headers, dict):
      columns = list(headers.keys())
    if isinstance(headers, list):
      columns = headers
    return pd.DataFrame(columns=columns)
  except Exception as e:
    self.log.error('Could not create DataFrame: %s', e)
    raise

def get_all_project_dirs(project_root: Path) -> list[Path]:
  """Get all directories in root that have soursdata/JATOS directories.

  Excludes all project that dose not have any data from JATOS.

  Args:
    project_root: The project root directory.

  Returns:
    A list with all project directories.
  """
  dirs = []
  for dir in project_root.iterdir():
    if Path(dir / config.JATOS_FOLDER).is_dir():
      dirs.append(dir)
  return dirs

def regex(text: str, regex: str, group: int | None = 0) -> str | re.Match:
  '''
  Get the matching regex from a string.

  PRE:
    regex should be a raw string, r''

  ARGS:
    text: The string that will be searched.
    regex: Raw string regex pattern to match against the text.
    group: Specify a subgroups of the match or None to return the whole result.

  RETURNS:
    str: The matching string or an empty string if nothing was found.
  '''
  result = re.search(regex, text)

  if not result:
    return ''

  if group is None:
    return result

  return result.group(group)

def convert_to_local_tz(date_ms: float) -> str:
  '''
  Convert an float to local timezone with the format (YYYY-MM-DD HH-mm-ss)

  PRE:
    date must be a date reprecented as miliseconds.

  ARGS:
    date_ms (float): A date reprecented as miliseconds.

  RETURNS:
    str: The time with the format (YYYY-MM-DD HH-mm-ss) converted to the local
    timezone.
  '''
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
