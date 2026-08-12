"""Download and process data from JATOS."""

# Standard library
import argparse
import datetime
import gzip
import io
import logging
import os
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Third-party
import pandas as pd
import requests
from dotenv import load_dotenv
from tqdm import tqdm

# Local
import config
import log as log_util
import utils

@dataclass
class StudyInfo:
  """Holds basic information about a study."""
  participant_id: int
  uuid: str
  title: str

@dataclass
class AppConfig:
  """Holds Basic settings for the server and project."""
  base_url: str
  api_token: str
  project_root: Path

@dataclass
class StudyState:
  """Holds the current study's state."""
  study_id:      int | None = None
  study_uuid:    str | None = None
  result_id:     str | None = None
  study_title:   str | None = None
  project_title: str | None = None

def get_args() -> argparse.Namespace:
  """
  Parses the command-line arguments.

    Returns: argparse.Namespace: Command-line arguments inputs as an
      argparse.Namespace object.
  """
  parser = argparse.ArgumentParser(
    prog='download',
    description='Download data from JATOS'
  )

  parser.add_argument(
    '-s',
    '--studies',
    nargs='*',
    help='one or more studies to download'
  )

  args = parser.parse_args()

  return args

class JatosDownloader:
  """Downloads data from a JATOS server.

  Attributes:
    app_config: A class containing base_url, api_token and project_root.
    args: User terminal arguments.
    log: Logger.
  """
  def __init__(
      self,
      app_config: AppConfig,
      args: argparse.Namespace,
      log: logging.Logger
  ):

    self.base_url = app_config.base_url
    self.headers = {'Authorization': f'Bearer {app_config.api_token}'}
    self.project_root = Path(app_config.project_root)
    self.args = args
    self.log = log

    self.session = requests.Session()
    self.session.headers.update(self.headers)

    self.state = StudyState()

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
      ValueError if url criteria is not fulfilled
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

    except requests.exceptions.RequestException as error:
      self.log.critical('Failed to fetch from URL: %s: %s', url, error)
      sys.exit(1)

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
          participant_id=item['id'],
          uuid=item['uuid'],
          title=item['title']
        )
        for item in data
      ]

    except requests.exceptions.JSONDecodeError as error:
      self.log.error('Invalid JSON response: %s', error)
      raise

    except KeyError as error:
      self.log.error(
        'Missing key in resposene: %s. Make sure that JATOS save all metadata '
        'for each study correctly.',
        error
      )
      raise

  def get_study_metadata(self, study_id: int) -> list[dict]:
    """Fetches study result metadata for a study.

    Args:
      study_id: The ID of a study.

    Returns:
      A list with dictionaries where each element is metadata for a study.

    Raises:
      requests.exceptions.JSONDecodeError: If the response could not be decoded
        into JSON.
      KeyError: If fetching the metadata was not successful.
    """
    url = f'{self.base_url}results/metadata'
    self.log.debug(
      'Fetching study metadata for %s ID %s',
      self.state.study_title,
      study_id
    )
    response = self._fetch(url, {'studyId': study_id})
    try:
      data = response.json()['data']
      study_result = data[0]['studyResults']

      return study_result

    except requests.exceptions.JSONDecodeError as error:
      self.log.error('Invalid JSON response: %s', error)
      raise

    except IndexError:
      self.log.debug(
        'Study %s ID %s have no results',
        self.state.study_title,
        study_id
      )
      raise

    except KeyError as error:
      self.log.error(
        'Failed to fetch metadata for study id %s: %s', study_id, error
      )
      raise

  def _get_pid(self, metadata: list[dict[Any, Any]]) -> str | None:
    for key in config.ID_KEYS:
      pid = metadata.get('urlQueryParameters', {}).get(key, None)
      if pid is not None:
        return pid
    self.log.debug(
      'Could not find participant ID for study %s result ID %s',
      self.state.study_title,
      self.state.result_id
    )
    return None

  def get_result_index_values(
      self,
      metadata: dict[str,Any]
  ) -> list[str | int | None]:
    """Get the result index values from a studies metadata.

    Args:
      metadata: A dictonary with metadata from a study.

    Returns:
      A list with metadata from a study.
    """
    data: list[str | int | None] = []

    data.append(self.state.study_title)

    self.state.result_id = metadata.get('id')
    data.append(self.state.result_id)

    self.log.debug(
      'Extracting result ID %s metadata values from study %s',
      self.state.result_id, self.state.study_title
    )

    data.append(metadata.get('uuid', None))
    data.append(self.state.study_id)
    data.append(self.state.study_uuid)

    date_start = metadata.get('startDate', None)
    if date_start:
      date_start = utils.convert_to_local_tz(date_start)
    data.append(date_start)

    date_last_seen = metadata.get('lastSeenDate', None)
    if date_last_seen:
      date_last_seen = utils.convert_to_local_tz(date_last_seen)
    data.append(date_last_seen)

    duration = metadata.get('duration', None)
    if duration:
      # Adding "'" so excel wont change the format.
      duration = "'" + duration
    data.append(duration)

    data.append(self._get_pid(metadata))
    data.append(metadata.get('studyState', None))
    data.append('-')
    data.append('not_downloaded')

    return data

  def get_result_data(self, result_id: int) -> io.BytesIO:
    """Fetches result data as a zip file.

    Args:
      result_id: Result id of a study.

    Returns:
      Result as io.BytesIO.
    """
    url = f'{self.base_url}results/data'
    self.log.debug('Fetching result data for result id %s', result_id)
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
      Exception: If unexpected error occurs.

    Side effects:
      Writes a .gz file to disk.
    """
    self.log.debug(
      'Saving rawdata %s to project %s',
      savepath.name, self.state.project_title
    )

    try:
      with zipfile.ZipFile(bytes_data) as zip_file:
        filename = zip_file.namelist()[0]

        with zip_file.open(filename) as content:
          data = content.read()

      with gzip.open(savepath, 'x', newline=None) as file:
        file.write(data)

    except FileExistsError:
      self.log.debug(
        'File %s exists, trying alternate names...',
        savepath.name
      )
      sufix: str = 1
      while True:
        try:
          filename_with_sufix = savepath.stem
          filename = Path(filename_with_sufix).stem
          new_savepath = savepath.with_stem(filename + f'_{sufix}' + '.txt')

          with gzip.open(new_savepath, 'x', newline=None) as file:
            file.write(data)

          self.log.debug('Saved as %s instead', new_savepath.name)
          break

        except FileExistsError:
          sufix += 1

        except Exception: # pylint: disable=broad-except
          self.log.exception(
            'Unexpected error while saving file: %s',
            new_savepath.name
          )

    except zipfile.BadZipFile as error:
      self.log.error('Failed to open zipfile: %s', error)
      raise

    except IndexError:
      self.log.debug(
        'No result found for %s', savepath.name
      )

    except Exception as error:
      self.log.exception('Failed to save file %s: %s', savepath.name, error)
      raise

  def load_or_create_result_index(self, path: Path) -> pd.DataFrame:
    """ Load or create result index tsv file.

    Args:
      path: Path to result index tsv.

    Returns:
      A DataFrame object with the content from the tsv or only the headers.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
      self.log.debug(
        'Found %s for project %s',
        config.RESULT_INDEX,
        self.state.project_title
      )
      result_index = pd.read_csv(
        path, dtype={"participant_id": "string"}, sep='\t'
      )
      return result_index

    self.log.debug(
      'Did not find %s for project %s, creating one',
      config.RESULT_INDEX,
      self.state.project_title
    )

    return pd.DataFrame(columns=config.RESULT_INDEX_HEADERS)

  @staticmethod
  def _filter_new_results(study_metadata, existing_uuids):
    results = []
    for row in study_metadata:
      if row.get('uuid') not in existing_uuids:
        results.append(row)
    return results

  def _append_new_result(self, result_index, rows):
    data = []
    for row in rows:
      try:
        data.append(self.get_result_index_values(row))

      except Exception: # pylint: disable=broad-except
        self.log.exception('Error appening result index values to data: ')

    new_df = pd.DataFrame(data, columns=result_index.columns)
    return pd.concat([new_df, result_index], ignore_index=True)

  def process_study(self, study: StudyInfo):
    """Download results and update result index.

    Args:
      study: Metadata for a study.

    Side effects: Saves files to disk.
    """
    # Variables for logging
    self.state.study_id = study.participant_id
    self.state.study_uuid = study.uuid
    self.state.study_title = study.title

    project_root = self.project_root / self.state.project_title
    result_index_path = project_root / config.RESULT_INDEX
    study_metadata = self.get_study_metadata(study.participant_id)
    result_index = self.load_or_create_result_index(result_index_path)
    existing_uuids = set(result_index['result_uuid'])

    new_rows = self._filter_new_results(study_metadata, existing_uuids)

    if new_rows:
      result_index = self._append_new_result(result_index, new_rows)

    result_index.to_csv(result_index_path, sep='\t', index=False)

  @staticmethod
  def _construct_result_filename(title: str, pid: str, rid: int) -> str:
    ses  = utils.regex(title, config.REGEX_PROJECT_SES)
    task = utils.regex(title, config.REGEX_PROJECT_TASK)

    filename = f'sub-{pid}_rid-{rid}_'
    if ses:
      filename += f'{ses}_'

    filename += f'{task}.txt.gz'
    return filename

  def _process_and_save_result(
      self,
      result_id: int,
      pid: str,
      title: str,
      target_dir: Path
  ):
    filename = self._construct_result_filename(title, pid, result_id)
    filepath = target_dir / filename

    bytes_data = self.get_result_data(result_id)
    self.save_result_data(bytes_data, filepath)

  def download_results(self, directory: Path):
    """Download all undownloaded results for a project and updates result index
    file.

    Args:
      directory: The path to the project.

    Side effects:
      Download and writes files to disk.
    """
    # pylint: disable=no-member

    self.state.project_title = directory.name
    result_index_path = directory / config.RESULT_INDEX
    result_index : pd.DataFrame = pd.read_csv(
      result_index_path, dtype={"participant_id": "string"}, sep='\t'
    )

    raw_data_dir = self.project_root / directory / config.RAW_DATA

    pending_rows = result_index[
      result_index['download_status'] != config.DOWNLOADED]

    if  pending_rows.empty:
      return

    pbar = tqdm(
      pending_rows.iterrows(),
      total=len(pending_rows),
      desc=f'Downloading {self.state.project_title}: '
    )

    for index, row in pbar:
      try:
        self._process_and_save_result(
          result_id=row['result_id'],
          pid=row['participant_id'],
          title=row['study_title'],
          target_dir=raw_data_dir
        )

        result_index.loc[index, 'download_status'] = config.DOWNLOADED
        result_index.loc[index, 'downloaded_at']  = \
          datetime.datetime.now().strftime(config.TIME_FORMAT)

      except Exception: # pylint: disable=broad-except
        self.log.exception(
          'Failed processing result id:%s, participant id: %s',
          row['result_id'], row['participant_id']
        )
        result_index.at[index, 'download_status'] = config.DOWNLOAD_FAILED

      result_index.to_csv(result_index_path, sep='\t', index=False)

  def run(self):
    """Execute the download workflow."""
    try:
      # Get project metadata and create result index
      studies = self.get_studies_info()
      pbar = tqdm(
        studies,
        total=len(studies),
        desc='Processing studies: '
      )
      for study in pbar:
        self.state.project_title = utils.regex(
          study.title, config.REGEX_PROJECT_TITLE
        )
        # Skip project if is not specified by the user
        if (
          self.args.studies
          and self.state.project_title not in self.args.studies
        ):
          continue
        try:
          self.process_study(study)
        except IndexError:
          continue
        except Exception: # pylint: disable=broad-except
          self.log.exception('Study failed: ')

      # Get result data and update result index
      project_dirs = utils.get_all_project_dirs(self.project_root)
      for project_dir in project_dirs:
        # Skip project if is not specified by the user
        if self.args.studies and project_dir.name not in self.args.studies:
          continue
        try:
          self.download_results(project_dir)
        except Exception: # pylint: disable=broad-except
          self.log.exception('Download failed: ')

    finally:
      self.log.info('Download completed')
      self.session.close()

def main():
  """Load configuration and start the downloader."""
  load_dotenv()
  app_config = AppConfig(
    os.getenv('BASE_URL'),
    os.getenv('API_TOKEN'),
    os.getenv('PROJECT_ROOT')
  )

  args = get_args()

  if (
      not app_config.base_url or
      not app_config.api_token or
      not app_config.project_root
  ):
    print('base_url, api_token and project_root must be set in .env file')
    sys.exit(1)

  log = log_util.setupLogging(app_config.project_root / config.DOWNLOAD_LOG)
  log.info('Configuration loaded successfully')

  downloader = JatosDownloader(app_config, args, log)
  downloader.run()

if __name__ == "__main__":
  main()
