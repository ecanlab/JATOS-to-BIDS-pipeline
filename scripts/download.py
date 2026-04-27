import os
import csv

BASE_DIR = '../raw_data'
METADATA_DIR = os.path.join(BASE_DIR, 'metadata')
STUDIES_FILE = os.path.join(METADATA_DIR, 'studies.csv')


class Csv:
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
        self.filepath = filepath

        # Ensure parent directory exists
        os.makedirs(METADATA_DIR, exist_ok=True)

        write_header = False

        if not os.path.isfile(filepath):
            write_header = True
        elif os.stat(filepath).st_size == 0:
            write_header = True

        self.f = open(filepath, 'a')
        self.writer = csv.writer(self.f)

        if write_header and header:
            self.writer.writerow(header)

    def write_row(self, row_data):
        self.writerow(row_data)
        self.f.flush()

    def close(self):
        self.f.close()

def main():
    studies = Csv(STUDIES_FILE, ['id', 'uuid', 'title'])

    studies.close()

if __name__ == "__main__":
    main()
