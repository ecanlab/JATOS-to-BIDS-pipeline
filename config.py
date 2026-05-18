from pathlib import Path

RESULT_INDEX = Path('sourcedata/JATOS/raw_data/result_index.csv')
RESULT_INDEX_HEADERS = [
  'result_id', 'result_uuid', 'study_id', 'study_uuid', 'start_date',
  'end_date', 'study_state', 'url_query_parameters', 'downloaded_at',
  'download_status',
]
