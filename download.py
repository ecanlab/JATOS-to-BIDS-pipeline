import os
import io
import gzip
import utils
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
      response = self.session.get(url, params=payload)
      response.raise_for_status()
      # Cookies need to be cleard after each call otherwise the call will be
      # redirected to the login page.
      self.session.cookies.clear_session_cookies()
      return response
    except requests.exceptions.RequestException as e:
      raise SystemExit(e)

  def get_project_ids(self) -> list[tuple[int,str]]:
    '''
    Fetches all IDs and project titles.
    RETURNS: A list of tuples where the first element is the id and the second
             is the title.
    '''
    url = f'{self.base_url}studies/properties'
    response = self._fetch(url)
    data = response.json().get("data", [])

    return ([(item.get('id'), item.get('uuid'), item.get('title'))
             for item in data])

  def get_study_metadata(self, study_id: int) -> list[dict] | None:
    '''
    Fetches study result metadata for a study.
    ARGS: study_id (int): The study id
    RETURNS: A list with dictionaries where every element is the metadata for a
             result.
    '''
    url = f'{self.base_url}results/metadata'
    response = self._fetch(url, {'studyId': study_id})
    data = response.json().get("data", [])
    if data:
      return data[0].get('studyResults')
    return None

  def get_result_index_values(
      self,
      metadata: dict[str],
      project_id: list[str]
  ) -> list[str]:
    '''
    Get the result index values from a studies metadata formated as a dictonary.
    PRE: metadata should be a dictonary.
         project_id should contain study id, study uuid and study title.
    ARGS: metadata (dict[str]): A dictonary with metadata from a study.
          project_id (list[str]): A list that contains study id, uuid and title.
    RETURNS: A list with strings.
    '''
    data = []
    data.append(project_id[2])
    data.append(metadata.get('id', None))
    data.append(metadata.get('uuid', None))
    data.append(project_id[0])
    data.append(project_id[1])

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

    return data

  def get_result_data(self, result_id: int) -> io.BytesIO:
    '''
    Fetches result data as a zip file.
    ARGS: id (int): The id of a result.
    RETURNS: _io.BytesIO.
    '''
    url = f'{self.base_url}results/data'
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
    zip_file = zipfile.ZipFile(bytes_data)
    file_name = zip_file.namelist()[0]
    with zip_file.open(file_name) as content:
      data = content.read()

    with gzip.open(savepath, 'wb') as f:
      f.write(data)

    content.close()
    f.close()

  def _load_or_create_result_index(self, path: Path) -> pd.DataFrame:
    '''
    Helper function to load or create result index csv file.
    ARGS: path (Path): Path to result index csv.
    RETURNS: A DataFrame object with the content from the csv or only the
             headers.
    '''
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
      df = pd.read_csv(path)
      return df
    return pd.DataFrame(columns=config.RESULT_INDEX_HEADERS)

  def _get_uuid_from_result_index(self, df: pd.DataFrame) -> set[str]:
    return set(df['result_uuid'])

  def _filter_new_results(self, study_metadata, existing_uuids):
    results = []
    for row in study_metadata:
      if row.get('uuid') not in existing_uuids:
        results.append(row)
    return results

  def _append_new_result(self, df, rows, id):
    data = [self.get_result_index_values(row, id) for row in rows]
    new_df = pd.DataFrame(data, columns=df.columns)
    return pd.concat([new_df, df], ignore_index=True)

  def process_project(self, id: int):
    '''
    Download results and update result index.
    ARGS: id (int): The projects id.
    SIDE_EFFECT: Saves files to disk.
    '''
    project_title  = utils.get_part_of_string(id[2], config.REGEX_PROJECT_TITLE)
    result_index_path = self.project_root / project_title / config.RESULT_INDEX
    df = self._load_or_create_result_index(result_index_path)
    existing_uuids = self._get_uuid_from_result_index(df)
    study_metadata = self.get_study_metadata(id[0])

    new_rows = self._filter_new_results(study_metadata, existing_uuids)

    if new_rows:
      df = self._append_new_result(df, new_rows, id)
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
    filename = self._construct_result_filename(title, id)
    filepath = target_dir / filename

    bytes_data = self.get_result_data(id)
    self.save_result_data(bytes_data, filepath)

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
        print(e)
        df.at[index, 'download_status'] = config.DOWNLOAD_FAILED
    df.to_csv(result_index_path, index=False)

  def run(self):
    try:
      # Get project metadata and create result index
      project_ids = self.get_project_ids()
      for project_id in project_ids:
        self.process_project(project_id)

      # Get result data and update result index
      project_dirs = [d for d in self.project_root.iterdir() if d.is_dir()]
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
