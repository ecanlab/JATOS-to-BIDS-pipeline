import datetime
from pathlib import Path

# Paths
RESULT_INDEX = Path('sourcedata/JATOS/raw_data/result_index.csv')

# Lists
RESULT_INDEX_HEADERS = [
  'study_title', 'result_id', 'result_uuid', 'study_id', 'study_uuid',
  'start_date', 'end_date', 'duration', 'participant_id', 'study_state',
  'downloaded_at', 'download_status',
]

# Regex
REGEX_PROJECT_TITLE = r'^[^_]+'

# Time
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# Get the local timezone
LOCAL_TZ = datetime.datetime.now().astimezone().tzinfo
