import os
import csv

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

if __name__ == "__main__":
    main()
