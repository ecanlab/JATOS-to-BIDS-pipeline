import os
import csv

BASE_DIR = '../raw_data'
METADATA_DIR = os.path.join(BASE_DIR, 'metadata')
STUDIES_FILE = os.path.join(METADATA_DIR, 'studies.csv')

class Csv:
    def __init__(self, filepath):
        if not os.path.isfile(filepath):
            os.makedirs(METADATA_DIR)
            
        self.csv = open(filepath, 'a', newline='')
        self.writer = csv.writer(self.csv, delimiter=' ')

def main():
    studies = Csv(STUDIES_FILE)

if __name__ == "__main__":
    main()
