import os
import utils
import config
import datetime
import requests
from pathlib import Path
from dotenv import load_dotenv
from csvHandler import CsvHandler

class JatosDownloader:
  def __init__(self, base_url: str, api_token: str, project_root: str):
    self.base_url = base_url
    self.headers = {'Authorization': f'Bearer {api_token}'}
    self.project_root = Path(project_root)
    self.session = requests.Session()
    self.session.headers.update(self.headers)
    self.project_ids: list[tuple[int,str]]

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
    response = self._fetch(url, {'download': False, 'studyId': study_id})
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
    data.append(datetime.datetime.now().strftime(config.TIME_FORMAT))
    data.append('False')

    return data


  def run(self):
    try:
      self.project_ids = self.get_project_ids()
      for project_id in self.project_ids:
        study_metadata = self.get_study_metadata(project_id[0])
        project_title  = utils.get_part_of_string(
          project_id[2],
          config.REGEX_PROJECT_TITLE
        )
        csv = CsvHandler(
          self.project_root / project_title / config.RESULT_INDEX,
          config.RESULT_INDEX_HEADERS
        )
        result_index_uuid_set = set(csv.get_column('result_uuid'))
        try:
          for row in study_metadata:
            if not row.get('uuid') in result_index_uuid_set:
              data = self.get_result_index_values(row, project_id)
              csv.write_row(data)

        except Exception as e:
          continue
        csv.close()

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
