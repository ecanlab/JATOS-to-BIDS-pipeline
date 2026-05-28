import re
import config
import datetime

def get_part_of_string(s: str, regex: str) -> str:
  '''
  Get the matching regex from a string.
  PRE: regex should be a raw string, r''
  ARGS: study_title (str): The study title that contains the project name.
        regex       (str): Raw string to match against the study_title.
  RETURNS: The matching string.
  '''
  result = re.search(regex, s)

  if result:
    return result.group(0)
  else:
    return ''

def convert_to_local_tz(date: float) -> str:
  '''
  Convert an int to local timezone with the format (YYYY-MM-DD HH-mm-ss)
  PRE: date must be a date reprecented as miliseconds.
  ARGS: date (str): A date reprecented as miliseconds.
  RETURN: A datetime.datetime object with the local timezone.
  '''
  # Convert the date in ms to UTC format
  start_date_utc = datetime.datetime.fromtimestamp(
    date / 1000.0,
    tz=datetime.timezone.utc
  )
  # Convert UTC to local time
  date_local_tz = start_date_utc.astimezone(config.LOCAL_TZ)

  # Apply format
  formatted_date = date_local_tz.strftime(config.TIME_FORMAT)

  return formatted_date
