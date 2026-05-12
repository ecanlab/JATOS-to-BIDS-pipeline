import os
import requests
import json
from dotenv import load_dotenv


class JatosDownloader:
  def __init__(self, base_url: str, api_token: str):
    self.base_url = base_url
    self.headers = {'Authorization': f'Bearer {api_token}'}
    self.session = requests.Session()
    self.session.headers.update(self.headers)
    self.project_ids: list[tuple[int,str]]
    self.project_metadata: list[dict]

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

  def get_project_ids(self) -> None:
    '''
    Fetches all IDs and project titles.
    SIDE EFFECT: Updates self.project_ids with a list of tuples where the first
                 element is the id and the second is the title.
    '''
    url = f'{self.base_url}studies/properties'
    response = self._fetch(url)
    data = response.json().get("data", [])

    self.project_ids = ([(item.get("id"), item.get("title")) for item in data])

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

  def run(self):
    try:
      self.get_project_ids()
      for project_id in self.project_ids:
        self.study_metadata = self.get_study_metadata(project_id[0])

    finally:
      self.session.close()

if __name__ == "__main__":
  load_dotenv()
  base_url  = os.getenv('base_url')
  api_token = os.getenv('api_token')

  if not base_url or not api_token:
    raise ValueError('base_url and api_token must be set in .env file')

  downloader = JatosDownloader(base_url, api_token)
  downloader.run()
