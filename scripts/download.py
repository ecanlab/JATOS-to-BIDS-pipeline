import os
import csv

class Csv:
    def __init__(self, name):
        self.csv = open(name, 'a', newline='')

def create_dir_structure():
    path = '../raw_data/metadata'
    if not os.path.isdir(path):
        os.makedirs(path, 0o444)

def main():
    create_dir_structure()
    studies = Csv('../raw_data/metadata/studies.csv')

if __name__ == "__main__":
    main()
