import os
import io
import gzip
import utils
import logging
import config
import zipfile
import datetime
import requests
import pandas as pd
import log as log_util
from pathlib import Path
from dotenv import load_dotenv
from typing import Any, NoReturn
from dataclasses import dataclass


@dataclass
class StudyInfo:
  id: int
  uuid: str
  title: str

class JatosDownloader:
  def __init__(
      self,
      base_url: str,
      api_token: str,
      project_root: str,
      log: logging.Logger):

    self.base_url = base_url
    self.headers = {'Authorization': f'Bearer {api_token}'}
    self.project_root = Path(project_root)
    self.log = log

    self.session = requests.Session()
    self.session.headers.update(self.headers)

    self.current_study_id:      int | None = None
    self.current_study_uuid:    int | None = None
    self.current_pid:           str | None = None
    self.current_result_id:     str | None = None
    self.current_study_title:   str | None = None
    self.current_project_title: str | None = None

  def _fetch(
      self,
      url: str,
      payload: dict[str,Any] | None = None
  ) -> requests.models.Response:
    """Fetches a response from a URL.

    Args:
       url: URL that must begin with "http://" or "https://".
       payload: Query parameters sent with the request.

    Returns:
      The HTTP response object.

    Raises:
      requests.exceptions.RequestException: If the request fails.
    """
    if not url.startswith(('http://', 'https://')):
      self.log.error('The URL must start with "http://" or "https://".')
      raise ValueError('The URL must start with "http://" or "https://".')

    try:
      self.log.debug('Connection to %s...', url)

      response = self.session.get(url, params=payload)
      response.raise_for_status()

      # Cookies need to be cleared after each call otherwise the request may be
      # redirected to the login page.

      self.session.cookies.clear_session_cookies()

      return response

    except requests.exceptions.RequestException as e:
      self.log.critical('Failed to fetch from URL: %s: %s', url, e)
      raise requests.exceptions.RequestException(
        f'Could not fetch from URL: %s, %s', url, e
      )

  def get_studies_info(self) -> list[StudyInfo]:
    """Fetches study ids, uuid and title from all studies on the JATOS server.

    Returns:
      A list of StudyInfo objects, each containing:
        - Study ID
        - Study UUID
        - Study title

    Raises:
      requests.exceptions.JSONDecodeError: If the response could not be decoded
      into JSON
    """
    self.log.info('Fetching study titles and ids')

    url = f'{self.base_url}studies/properties'
    response = self._fetch(url)

    try:
      data = response.json()['data']

      return [
        StudyInfo(
          id=item['id'],
          uuid=item['uuid'],
          title=item['title']
        )
        for item in data
      ]

    except requests.exceptions.JSONDecodeError:
      self.log.exception('Invalid JSON response')
      raise

    except KeyError:
      self.log.exception(
        'Missing key in resposene. Make sure that JATOS save all metadata for'
        'each study correctly.'
      )
      raise

  def get_study_metadata(self, study_id: int) -> list[dict]:
    '''Fetches study result metadata for a study.

    Args:
      study_id: The id of the study.

    Returns:
      A list with dictionaries where each element is metadata for a study.

    Raises:
      requests.exceptions.JSONDecodeError: If the response could not be decoded
      into JSON
    '''
    url = f'{self.base_url}results/metadata'
    self.log.info('Fetching study metadata for study id %s', study_id)
    response = self._fetch(url, {'studyId': study_id})
    try:
      data = response.json()['data']
      study_result = data[0]['studyResults']

      return study_result

    except requests.exceptions.JSONDecodeError:
      self.log.exception('Invalid JSON response')
      raise

    except KeyError:
      self.log.exception('Failed to fetch metadata for study id %s', study_id)
      raise

  def get_result_index_values(
      self,
      metadata: dict[str,Any]
  ) -> list[str | None]:
    """ Get the result index values from a studies metadata.

    Args:
      metadata: A dictonary with metadata from a study.

    Returns:
      A list with strings or None.
    """
    data = []

    data.append(self.current_study_title)

    result_id = metadata.get('id', None)
    data.append(result_id)
    self.current_result_id = result_id

    self.log.info(
      'Extracting result metadata values from study %s with id %s',
      self.current_study_title, self.current_result_id
    )

    data.append(metadata.get('uuid', None))

    data.append(self.current_study_id)
    data.append(self.current_study_uuid)

    date_start = metadata.get('startDate', None)
    if date_start:
      date_start_local_tz = utils.convert_to_local_tz(date_start)
    data.append(date_start_local_tz)

    date_last_seen = metadata.get('lastSeenDate', None)
    if date_last_seen:
      date_last_seen_local_tz = utils.convert_to_local_tz(date_last_seen)
    data.append(date_last_seen_local_tz)

    data.append(metadata.get('duration', None))

    data.append(metadata.get('urlQueryParameters', {}).get('pid', None))
    data.append(metadata.get('studyState', None))
    data.append('-')
    data.append('not_downloaded')

    return data

  def _get_pid(self, metadata: list[dict[Any, Any]]) -> str:
    return metadata[0].get('urlQueryParameters', {}).get('pid', None)

  def get_result_data(self, result_id: int) -> io.BytesIO:
    """ Fetches result data as a zip file.

    Args:
      id: Result id of a study.

    Returns:
      io.BytesIO.
    """
    url = f'{self.base_url}results/data'
    self.log.info('Fetching result data for result id %s', result_id)
    response = self._fetch(url, {'studyResultId': result_id})
    bytes_data = io.BytesIO(response.content)

    return bytes_data

  def save_result_data(self, bytes_data: io.BytesIO, savepath: Path):
    """ Save result data as a .gz file.

    Args:
      bytes_data: ZIP archive containing a single text file.
      savepath: Destination path for the output .gz file.

    Raises:
      zipfile.BadZipFile: If bytes_data does not contains a valid ZIP archive.
      OSError: If the output file cannot be written.

    Side effects:
      Writes a .gz file to disk.
    """
    self.log.info(
      'Saving rawdata %s to project %s directory',
      savepath.name, self.current_project_title
    )

    try:
      zip_file = zipfile.ZipFile(bytes_data)
      file_name = zip_file.namelist()[0]
      with zip_file.open(file_name) as content:
        data = content.read()

      with gzip.open(savepath, 'wb') as f:
        f.write(data)

    except zipfile.BadZipFile:
      self.log.exception('Failed to open zipfile')
      raise

    except Exception:
      self.log.exception('Failed to save file %s', savepath.name)
      raise

  def load_or_create_result_index(self, path: Path) -> pd.DataFrame:
    """ Load or create result index csv file.

    Args:
      path: Path to result index csv.

    Returns:
      A DataFrame object with the content from the csv or only the headers.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
      self.log.info(
        'Found result_index_file.csv for project %s',
        self.current_project_title
      )
      df = pd.read_csv(path)
      return df

    self.log.info(
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

  def process_study(self, study: StudyInfo):
    """Download results and update result index.

    Args:
      study: Metadata for a study.

    Side effects: Saves files to disk.
    """
    project_title = utils.get_part_of_string(
      study.title,
      config.REGEX_PROJECT_TITLE
    )
    result_index_path = self.project_root / project_title / config.RESULT_INDEX
    study_metadata = self.get_study_metadata(study.id)

    # Variables for logging
    self.current_study_id = study.id
    self.current_study_uuid = study.uuid
    self.current_pid = self._get_pid(study_metadata)
    if not self.current_pid:
      self.log.warning(
        'Could not get pid from study %s resultd id %s, all studies needs to'
        ' pid in urlQueryParameters or in data as either pid or id',
        study.title, self.current_result_id
      )
    self.current_study_title = study.title
    self.current_project_title = project_title

    df = self.load_or_create_result_index(result_index_path)
    existing_uuids = set(df['result_uuid'])

    new_rows = self._filter_new_results(study_metadata, existing_uuids)

    if new_rows:
      df = self._append_new_result(df, new_rows)
      df.to_csv(result_index_path, index=False)

  def _construct_result_filename(self, title: str, pid: str) -> str:
    arm  = utils.get_part_of_string(title, config.REGEX_PROJECT_ARM)
    ses  = utils.get_part_of_string(title, config.REGEX_PROJECT_SES)
    task = utils.get_part_of_string(title, config.REGEX_PROJECT_TASK)
    return f'pid-{pid}{arm}{ses}{task}.txt.gz'

  def _process_and_save_result(
      self,
      result_id: int,
      pid: str,
      title: str,
      target_dir: Path
  ):
    filename = self._construct_result_filename(title, pid)
    filepath = target_dir / filename

    bytes_data = self.get_result_data(result_id)
    self.save_result_data(bytes_data, filepath)

  def _get_all_project_dirs(self) -> list[Path]:
    """Get all directories in root that have soursdata/JATOS directories.
    Excludes all project that dose not have any data from JATOS.
    """
    dirs = []
    for dir in self.project_root.iterdir():
      if Path(dir / config.JATOS_FOLDER).is_dir():
        dirs.append(dir)
    return dirs

  def download_results(self, directory: Path):
    """Download all undownloaded results for a project and updates result index
    file.

    Args:
      directory: The path to the project.

    Side effects:
      Download and writes files to disk.
    """
    result_index_path = directory / config.RESULT_INDEX
    df = pd.read_csv(result_index_path)

    raw_data_dir = self.project_root / directory / config.RAW_DATA

    pending_rows = df[df['download_status'] != config.DOWNLOADED]

    for index, row in pending_rows.iterrows():
      try:
        self._process_and_save_result(
          result_id=row['result_id'],
          pid=row['participant_id'],
          title=row['study_title'],
          target_dir=raw_data_dir
        )
        df.at[index, 'download_status'] = config.DOWNLOADED
        df.at[index, 'downloaded_at']  = \
          datetime.datetime.now().strftime(config.TIME_FORMAT)

      except Exception:
        self.log.exception(
          'Failed processing result id:%s, participant id: %s',
          row['result_id'], row['participant_id']
        )
        df.at[index, 'download_status'] = config.DOWNLOAD_FAILED
    df.to_csv(result_index_path, index=False)

  def run(self):
    try:
      # Get project metadata and create result index
      studies = self.get_studies_info()
      for study in studies:
        try:
          self.process_study(study)
        except Exception:
          self.log.exception("Study failed: %s", study)

      # Get result data and update result index
      project_dirs = self._get_all_project_dirs()
      for project_dir in project_dirs:
        try:
          self.download_results(project_dir)
        except Exception:
          self.log.exception("Download failed")

    finally:
      self.session.close()

if __name__ == "__main__":
  load_dotenv()
  base_url  = os.getenv('base_url')
  api_token = os.getenv('api_token')
  project_root = os.getenv('project_root')

  if not base_url or not api_token or not project_root:
    print('base_url, api_token and project_root must be set in .env file')
    exit()

  log = log_util.setupLogging(project_root / config.DOWNLOAD_LOG)
  log.info('Configuration loaded successfully')

  downloader = JatosDownloader(base_url, api_token, project_root, log)
  downloader.run()
