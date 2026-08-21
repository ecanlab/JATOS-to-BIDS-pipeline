import datetime
from enum import Enum
from pathlib import Path

# Paths
SOURCE_JATOS        = Path('sourcedata/JATOS')
RAW_DATA            = Path('sourcedata/JATOS/raw_data/')
RESULT_INDEX        = Path(RAW_DATA / 'result_index.tsv')
PROJECT_CONFIG      = Path('code/JATOS/project_config.json')
CODE_JATOS          = Path('code/JATOS/')
VALIDATED_DATA      = Path('sourcedata/JATOS/validated_data')
VALIDATION_PROTOCOL = Path(VALIDATED_DATA / 'validation_protocol.tsv')
DOWNLOAD_LOG        = Path('code/JATOS/logs/download.log')
VALIDATE_LOG        = Path('code/JATOS/logs/validate.log')

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
REGEX_PROJECT_SES    = r'ses-[^_]+'
REGEX_PROJECT_TASK   = r'task-[^.]+'
REGEX_SUB            = r'sub-([^_]+)'
REGEX_RESULT_RID     = r'rid-([^_]+)'
REGEX_TASK_NAME      = r'^(?:(?!\bv\.\d+(?:\.\d+)*\b).)*'
REGEX_TASK_VERSION   = r'v\.\d+(?:\.\d+)*'

# Time
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

# Get the local timezone
LOCAL_TZ = datetime.datetime.now().astimezone().tzinfo

# ID keys
ID_KEYS = ['pid', 'PID', 'id', 'ID']

# Title keys
TITLE_KEYS = ['test_version']

# ID correction actions
class Action(Enum):
  KEEP = 'keep'
  REASSIGN_ID = 'reassign_id'
  EXCLUDE = 'exclude'

actions = {action.value for action in Action}
