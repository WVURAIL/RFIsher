"""The records' reads of their input files: each file is closed once it is read."""
import csv
import json


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def read_rows(path):
    """The rows of a CSV file, as csv.DictReader gives them."""
    with open(path) as fh:
        return list(csv.DictReader(fh))
