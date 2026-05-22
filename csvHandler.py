import csv
from pathlib import Path

class CsvHandler:
  """This class handels csv files.

  The class makes the folder path if it dose not exist. It opens the
  csv file in append mode.

  Args:
    filepath (str): File path to where the csv will be created or
      opened.
    header (list[str]): A list of string used as headers in the csv
      file.
  """
  def __init__(self, filepath: str, header: list[str] = None):
    self.filepath = Path(filepath)
    self.header = header
    self.write_header = False

    if not self.filepath.exists():
      self.write_header = True

    Path(self.filepath).parent.mkdir(parents=True, exist_ok=True)

    self.f = open(self.filepath, 'a+', newline='')
    self.writer = csv.writer(self.f)
    if self.write_header and self.header:
      self.writer.writerow(self.header)

  def write_row(self, row_data: list[str]):
    self.writer.writerow(row_data)
    self.f.flush()

  def get_column(self, headers: str | list[str]) -> list[str] | list[list[str]]:
    self.f.seek(0) # Set the reader at the beginning of the file.
    reader = csv.DictReader(self.f)

    if isinstance(headers, str):
      headers = [headers]

    columns_data = [[] for _ in headers]

    for row in reader:
      for i, header in enumerate(headers):
        columns_data[i].append(row.get(header))

    self.f.seek(0,2) # Set the reader at the end of the file.
    if len(columns_data) == 1:
      return columns_data[0]

    return columns_data

  def close(self):
    self.f.close()
