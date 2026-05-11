import os
import requests
from dotenv import load_dotenv


class JatosDownloader:
  def __init__(self, base_url: str, api_token: str):
    self.base_url = base_url
    self.headers = {'Authorization': f'Bearer {api_token}'}
    self.session = requests.Session()
    self.session.headers.update(self.headers)
    self.project_ids = [(int,str)]

  def _fetch(self, url) -> requests.exceptions.RequestException:
    '''
    _fetch is a helper function that fetches responses from a url.
    ARGS: url (str): A url string that should begin with http://
    PRE: url should start with "http://".
    RETURNS: A requests.models.Response
    '''
    try:
      response = self.session.get(url)
      response.raise_for_status()
      return response
    except requests.exceptions.RequestException as e:
      raise SystemExit(e)

  def get_project_ids(self):
    '''
    Fetches all IDs and project titles.
    SIDE EFFECT: Update self.project_ids with a list with tuples where the first
                 element is the id and the second is the title.
    '''
    url = f'{self.base_url}studies/properties'
    response = self._fetch(url)
    data = response.json().get("data", [])
    self.project_ids = ([(item.get("id"), item.get("title")) for item in data])

  def run(self):
    try:
      self.get_project_ids()
    finally:
      self.session.close()

if __name__ == "__main__":
  load_dotenv()
  base_url  = os.getenv('base_url')
  api_token = os.getenv('api_token')

  downloader = JatosDownloader(base_url, api_token)
  downloader.run()
