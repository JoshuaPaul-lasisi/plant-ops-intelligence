"""
Load every CSV in a folder into a BigQuery dataset, one table per file.

Needs google-cloud-bigquery and application default credentials:
    pip install google-cloud-bigquery pyarrow
    gcloud auth application-default login

Usage:
    python src/load_to_bigquery.py --project nitrogen-plant-operations --dataset nitrochem_ngu --folder data/raw
"""

import argparse
from pathlib import Path

import pandas as pd


def load_folder(folder, project, dataset, location="US"):
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    ds = bigquery.Dataset(f"{project}.{dataset}")
    ds.location = location
    client.create_dataset(ds, exists_ok=True)

    for path in sorted(Path(folder).glob("*.csv")):
        df = pd.read_csv(path)
        for c in df.columns:
            if c in ("timestamp", "date") or c.endswith("_time") or c.startswith("fault_"):
                df[c] = pd.to_datetime(df[c])
        table_id = f"{project}.{dataset}.{path.stem}"
        job = client.load_table_from_dataframe(
            df, table_id, job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"))
        job.result()
        print(f"{table_id}: {client.get_table(table_id).num_rows:,} rows")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="nitrogen-plant-operations")
    ap.add_argument("--dataset", default="nitrochem_ngu")
    ap.add_argument("--folder", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "raw")
    ap.add_argument("--location", default="US")
    a = ap.parse_args()
    load_folder(a.folder, a.project, a.dataset, a.location)
