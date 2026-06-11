import re
import config
import datetime
from pathlib import Path

def get_all_project_dirs(project_root) -> list[Path]:
  """Get all directories in root that have soursdata/JATOS directories.
  Excludes all project that dose not have any data from JATOS.
  """
  dirs = []
  for dir in project_root.iterdir():
    if Path(dir / config.JATOS_FOLDER).is_dir():
      dirs.append(dir)
  return dirs

def get_part_of_string(text: str, regex: str) -> str:
  '''
  Get the matching regex from a string.

  PRE:
    regex should be a raw string, r''

  ARGS:
    text (str): The string that will be searched.
    regex (str): Raw string regex pattern to match against the text.

  RETURNS:
    str: The matching string or an empty string if nothing was found.
  '''
  result = re.search(regex, text)

  if result:
    return result.group(0)
  else:
    return ''

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
