import argparse
from pathlib import Path
import typesense
from tqdm import tqdm
import json

client = typesense.Client({
  'nodes': [{
    'host': 'localhost',
    'port': '8108',
    'protocol': 'http'
  }],
  'api_key': 'xyz',
  'connection_timeout_seconds': 5
})


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("files_path")

  args = parser.parse_args()

  state_code = Path(args.files_path).parents[0].name
  missing_files = []

  for file_name in tqdm(Path(args.files_path).iterdir()):
    try:
      client.collections['legislature_debates'].documents[f"{state_code}-{file_name.name}"].retrieve()
    except Exception as e:
      print(e)
      missing_files.append((state_code, file_name.name, e))

  with open("errors.json", "w") as f:
    json.dump(missing_files, f)


if __name__ == "__main__":
  main()
