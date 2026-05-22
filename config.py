import datetime
from pathlib import Path

# Paths
RAW_DATA     = Path('sourcedata/JATOS/raw_data/')
RESULT_INDEX = Path(RAW_DATA / 'result_index.csv')


# Lists
RESULT_INDEX_HEADERS = [
  'study_title', 'result_id', 'result_uuid', 'study_id', 'study_uuid',
  'start_date', 'end_date', 'duration', 'participant_id', 'study_state',
  'downloaded_at', 'download_status',
]

# Regex
REGEX_PROJECT_TITLE  = r'^[^_]+'
REGEX_PROJECT_ARM    = r'_arm-[\d]+'
REGEX_PROJECT_SES    = r'_ses-[\d]+'
REGEX_PROJECT_TASK   = r'_task-[\w]+'

# Time
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# Get the local timezone
LOCAL_TZ = datetime.datetime.now().astimezone().tzinfo
