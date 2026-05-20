import config
import datetime

def convert_to_local_tz(date: int) -> datetime.datetime:
  '''
  Convert an int to local timezone with the format (YYYY-MM-DD HH-mm-ss)
  PRE: date must be a date reprecented as miliseconds.
  ARGS: date (int): A date reprecented as miliseconds.
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
