import os
import io
import gzip
import utils
import logger
import config
import zipfile
import datetime
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

class JatosDownloader:
  def __init__(self, base_url: str, api_token: str, project_root: str):
    self.base_url = base_url
    self.headers = {'Authorization': f'Bearer {api_token}'}
    self.project_root = Path(project_root)
    self.session = requests.Session()
    self.session.headers.update(self.headers)

    self.current_study_id = ''
    self.current_pid = ''
    self.current_result_id = ''
    self.current_study_title = ''
    self.current_project_title = ''


    self.logger = logger.setupLogging(self.project_root / config.DOWNLOAD_LOG)

  def _fetch(
      self,
      url: str,
      payload: dict | None = None
  ) -> requests.models.Response:
    '''
    Helper function that fetches responses from a url.
    ARGS: url (str): A url string that should begin with http://
          payload (dict): Data to send with the request
    PRE: url should start with "http://".
    RETURNS: A requests.models.Response
    '''
    try:
      self.logger.debug('Connection to %s...', url)
      response = self.session.get(url, params=payload)
      response.raise_for_status()
      # Cookies need to be cleard after each call otherwise the call will be
      # redirected to the login page.
      self.session.cookies.clear_session_cookies()
      return response
    except requests.exceptions.RequestException as e:
      self.logger.critical('Failed to fetch %s: %s', url, e)
      exit()

  def get_studies_info(self) -> tuple[list[int], list[str], list[str]]:
    '''
    Fetches study titles and ids.
    RETURNS: A three lists where the first is the ids, the second
             is the uuids and the third is the titles.
    '''
    self.logger.info('Fetching study titles and ids')
    url = f'{self.base_url}studies/properties'
    response = self._fetch(url)
    try:
      data   = response.json().get("data", [])
      ids    = [item.get('id') for item in data]
      uuids  = [item.get('uuid') for item in data]
      titles = [item.get('title') for item in data]
      return ids, uuids, titles
    except Exception as e:
      self.logger.ctitical('Failed to fetch study titles and ids: %s', e)
      self.logger.debug('Response body: %s', response.text[:500])

  def get_study_metadata(self, study_id: int) -> list[dict] | None:
    '''
    Fetches study result metadata for a study.
    ARGS: study_id (int): The study id
    RETURNS: A list with dictionaries where every element is the metadata for a
             result.
    '''
    url = f'{self.base_url}results/metadata'
    self.logger.info('Fetching study metadata for study id %s', study_id)
    response = self._fetch(url, {'studyId': study_id})
    try:
      data = response.json().get("data", [])
      study_result = data[0].get('studyResults', None)

      return study_result
    except Exception as e:
      self.logger.error(
        'Failed to fetch metadata for study id %s: %s', study_id, e
      )
      return None

  def get_result_index_values(self, metadata: dict[str]) -> list[str]:
    '''
    Get the result index values from a studies metadata formated as a dictonary.
    PRE: metadata should be a dictonary.
    ARGS: metadata (dict[str]): A dictonary with metadata from a study.
    RETURNS: A list with strings.
    '''
    data = []

    try:
      data.append(self.current_study_title)

      result_id = metadata.get('id', None)
      data.append(result_id)
      self.current_result_id = result_id

      self.logger.info(
        'Extracting result metadata values from study %s with id %s',
        self.current_study_title, self.current_result_id
      )

      data.append(metadata.get('uuid', None))

      data.append(metadata.get('study_id', None))
      data.append(metadata.get('study_uuid', None))

      date_start = metadata.get('startDate', None)
      date_start_local_tz = utils.convert_to_local_tz(date_start)
      data.append(date_start_local_tz)

      date_last_seen = metadata.get('lastSeenDate', None)
      date_last_seen_local_tz = utils.convert_to_local_tz(date_last_seen)
      data.append(date_last_seen_local_tz)

      data.append(metadata.get('duration', None))
      data.append(metadata.get('urlQueryParameters', None).get('pid', None))
      data.append(metadata.get('studyState', None))
      data.append('-')
      data.append('not_downloaded')

    except Exception as e:
      self.logger.error(
        'Failed to result extracted metadata values from study %s with id %s:'
        ' %s',
        self.current_study_title, self.current_result_id, e
      )
    return data

  def _get_pid(self, metadata: dict[str]) -> str:
    return metadata[0].get('urlQueryParameters', None).get('pid', None)

  def get_result_data(self, result_id: int) -> io.BytesIO:
    '''
    Fetches result data as a zip file.
    ARGS: id (int): The id of a result.
    RETURNS: _io.BytesIO.
    '''
    url = f'{self.base_url}results/data'
    self.logger.info('Fetching result data for result id %s', result_id)
    response = self._fetch(url, {'studyResultId': result_id})
    bytes_data = io.BytesIO(response.content)

    return bytes_data

  def save_result_data(self, bytes_data: io.BytesIO, savepath: Path):
    '''
    Save result data as a .gz file.
    PRE: bytes_data must encode a ZipFile and only contain one .txt file.
    ARGS: save_path (Path): The path where the .gz file will be saved.
    SIDE_EFFECT: Saves file to disk.
    '''
    self.logger.info(
      'Saving rawdata %s to project %s folder',
      savepath.name, self.current_project_title
    )
    try:
      zip_file = zipfile.ZipFile(bytes_data)
      file_name = zip_file.namelist()[0]
      with zip_file.open(file_name) as content:
        data = content.read()

      with gzip.open(savepath, 'wb') as f:
        f.write(data)
    except Exception as e:
      self.logger.error('Failed to save file %s: %s', savepath.name, e)

  def _load_or_create_result_index(self, path: Path) -> pd.DataFrame:
    '''
    Helper function to load or create result index csv file.
    ARGS: path (Path): Path to result index csv.
    RETURNS: A DataFrame object with the content from the csv or only the
             headers.
    '''
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
      self.logger.info(
        'Found result_index_file.csv for project %s',
        self.current_project_title
      )
      df = pd.read_csv(path)
      return df
    self.logger.info(
      'Did not find result_index_file.csv for project %s, creating one',
      self.current_project_title
    )
    return pd.DataFrame(columns=config.RESULT_INDEX_HEADERS)

  def _filter_new_results(self, study_metadata, existing_uuids):
    results = []
    for row in study_metadata:
      if row.get('uuid') not in existing_uuids:
        results.append(row)
    return results

  def _append_new_result(self, df, rows):
    data = [self.get_result_index_values(row) for row in rows]
    new_df = pd.DataFrame(data, columns=df.columns)
    return pd.concat([new_df, df], ignore_index=True)

  def process_study(self, study_id: int, study_uuid: str, study_title):
    '''
    Download results and update result index.
    ARGS: study_id (int): The study id.
          study_uuid (str): The study uuid.
          title (str): The study title.
    SIDE_EFFECT: Saves files to disk.
    '''
    project_title = utils.get_part_of_string(
      study_title,
      config.REGEX_PROJECT_TITLE
    )
    result_index_path = self.project_root / project_title / config.RESULT_INDEX
    study_metadata = self.get_study_metadata(study_id)

    # Variables for logging
    self.current_study_id = study_id
    self.current_pid = self._get_pid(study_metadata)
    if not self.current_pid:
      self.logger.warrning(
        'Could not get pid from study %s resultd id %s, all studies needs to'
        ' pid in urlQueryParameters or in data as either pid or id',
        study_title, self.current_result_id
      )
    self.current_study_title = study_title
    self.current_project_title = project_title

    df = self._load_or_create_result_index(result_index_path)
    existing_uuids = set(df['result_uuid'])

    new_rows = self._filter_new_results(study_metadata, existing_uuids)

    if new_rows:
      df = self._append_new_result(df, new_rows)
      df.to_csv(result_index_path, index=False)

  def _construct_result_filename(self, title: str, pid: int) -> str:
    arm  = utils.get_part_of_string(title, config.REGEX_PROJECT_ARM)
    ses  = utils.get_part_of_string(title, config.REGEX_PROJECT_SES)
    task = utils.get_part_of_string(title, config.REGEX_PROJECT_TASK)
    return f'pid-{pid}{arm}{ses}{task}.txt.gz'

  def _process_and_save_result(
      self,
      id: int,
      pid: str,
      title: str,
      target_dir: Path
  ):
    filename = self._construct_result_filename(title, pid)
    filepath = target_dir / filename

    bytes_data = self.get_result_data(id)
    self.save_result_data(bytes_data, filepath)

  def _get_all_project_dirs(self) -> list[Path]:
    '''
    Get all folders in root that have soursdata/JATOS folders.
    Excludes all project that dose not have any data from JATOS.
    '''
    dirs = []
    for dir in self.project_root.iterdir():
      if Path(dir / config.JATOS_FOLDER).is_dir():
        dirs.append(dir)
    return dirs

  def download_results(self, directory: Path):
    '''
    Download all undownloaded results for a project and updates result index
    file.
    ARGS: directory (Path): The path to the project.
    SIDE_EFFECT: Download and writes files to disk.
    '''
    result_index_path = directory / config.RESULT_INDEX
    df = pd.read_csv(result_index_path)

    raw_data_dir = self.project_root / directory / config.RAW_DATA

    pending_rows = df[df['download_status'] != config.DOWNLOAD_COMPLETE]

    for index, row in pending_rows.iterrows():
      try:
        self._process_and_save_result(
          id=row['result_id'],
          pid=row['participant_id'],
          title=row['study_title'],
          target_dir=raw_data_dir
        )
        df.at[index, 'download_status'] = config.DOWNLOAD_COMPLETE
        df.at[index, 'downloaded_at']  = \
          datetime.datetime.now().strftime(config.TIME_FORMAT)

      except Exception as e:
        df.at[index, 'download_status'] = config.DOWNLOAD_FAILED
    df.to_csv(result_index_path, index=False)

  def run(self):
    try:
      # Get project metadata and create result index
      study_ids, study_uuids, titles = self.get_studies_info()
      for study_id, study_uuid, title in zip(study_ids, study_uuids, titles):
        self.process_study(study_id, study_uuid, title)

      # Get result data and update result index
      project_dirs = self._get_all_project_dirs()
      for project_dir in project_dirs:
        self.download_results(project_dir)

    finally:
      self.session.close()

if __name__ == "__main__":
  load_dotenv()
  base_url  = os.getenv('base_url')
  api_token = os.getenv('api_token')
  project_root = os.getenv('project_root')

  if not base_url or not api_token or not project_root:
    raise ValueError('base_url and api_token must be set in .env file')

  downloader = JatosDownloader(base_url, api_token, project_root)
  downloader.run()
