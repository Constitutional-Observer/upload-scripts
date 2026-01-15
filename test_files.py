import argparse
from pathlib import Path
import typesense
from tqdm import tqdm

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

  state_code = Path("args.files_path").parents[0].name
  for file_name in tqdm(Path(args.files_path).iterdir()):
    try:
      client.collections['legislature_debates'].documents[f"{state_code}-{file_name}"].retrieve()
    except Exception as e:
      print(e)


if __name__ == "__main__":
  main()
