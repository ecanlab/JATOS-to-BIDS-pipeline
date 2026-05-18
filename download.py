import os
import re
import requests
import config
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

  def _fetch(self,
             url: str,
             payload: dict | None = None) -> requests.models.Response:
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

    return ([(item.get("id"), item.get("title")) for item in data])

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

  def get_part_of_string(self, s: str, regex: str) -> str:
    '''
    Gets the matching regex from a string.
    PRE: regex should be a raw string, r''
    ARGS: study_title (str): The study title that contains the project name
          regex       (str): Raw string to match against the study_title
    RETURNS: The matching string.
    '''
    result = re.search(regex, s)

    if result:
      return result.group(0)

  def run(self):
    try:
      self.project_ids = self.get_project_ids()
      for project_id in self.project_ids:
        study_metadata = self.get_study_metadata(project_id[0])
        project_title  = self.get_part_of_string(project_id[1], r'^[^_]+')
        csv = CsvHandler(
          self.project_root / project_title / config.RESULT_INDEX,
          config.RESULT_INDEX_HEADERS
        )
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
