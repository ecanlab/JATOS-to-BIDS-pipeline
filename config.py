import datetime
from pathlib import Path

# Paths
JATOS_FOLDER = Path('sourcedata/JATOS')
RAW_DATA     = Path('sourcedata/JATOS/raw_data/')
RESULT_INDEX = Path(RAW_DATA / 'result_index.csv')
NORMALIZED_DATA = Path('sourcedata/JATOS/normalized_data')
SCHEMA_MAP = Path('code/JATOS/schema_map.json')
DOWNLOAD_LOG = Path('code/JATOS/logs/download.log')
NORMALIZE_LOG = Path('code/JATOS/logs/normalize.log')

# Download states
DOWNLOADED = 'downloaded'
DOWNLOAD_FAILED   = 'failed'

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
REGEX_TASK_NAME      = r'^(?:(?!\bv\.\d+(?:\.\d+)*\b).)*'
REGEX_TASK_VERSION   = r'v\.\d+(?:\.\d+)*'

# Time
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# Get the local timezone
LOCAL_TZ = datetime.datetime.now().astimezone().tzinfo
