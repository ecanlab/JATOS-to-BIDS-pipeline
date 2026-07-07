import datetime
from enum import Enum
from pathlib import Path

# Paths
JATOS_FOLDER   = Path('sourcedata/JATOS')
RAW_DATA       = Path('sourcedata/JATOS/raw_data/')
RESULT_INDEX   = Path(RAW_DATA / 'result_index.csv')
PROJECT_CONFIG = Path('code/JATOS/project_config.json')
VALIDATED_DATA = Path('sourcedata/JATOS/validated_data')
ID_CORRECTIONS = Path(VALIDATED_DATA / 'id_corrections.csv')
DOWNLOAD_LOG   = Path('code/JATOS/logs/download.log')
VALIDATE_LOG   = Path('code/JATOS/logs/validate.log')

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
REGEX_PROJECT_ARM    = r'_arm-[^_]+'
REGEX_PROJECT_SES    = r'_ses-[^_]+'
REGEX_PROJECT_TASK   = r'_task-[^_]+'
REGEX_RESULT_PID     = r'pid-([^_]+)'
REGEX_RESULT_RID     = r'_rid-([^_]+)'
REGEX_TASK_NAME      = r'^(?:(?!\bv\.\d+(?:\.\d+)*\b).)*'
REGEX_TASK_VERSION   = r'v\.\d+(?:\.\d+)*'

# Time
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

# Get the local timezone
LOCAL_TZ = datetime.datetime.now().astimezone().tzinfo

# ID correction rules
class Rule(Enum):
  KEEP = 'keep'
  REASSIGN_ID = 'reassign_id'
  EXCLUDE = 'exclude'

rules = {rule.value for rule in Rule}
