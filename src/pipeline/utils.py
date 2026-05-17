import json
import os
import re
from typing import Any

import pandas as pd

from google.api_core.exceptions import NotFound
from google.cloud import bigquery
from pandas.api import types as pdt
from src.google import get_storage_bucket


def to_dict_safe(model):
    """Convert Pydantic model to dict."""
    try:
        return model.model_dump()
    except Exception:
        return dict(model)


def upload_file_to_gcs(bucket_name: str, source_file: str, dest_path: str) -> str:
    """Upload file to GCS and return gs:// URI."""
    _, bucket = get_storage_bucket(bucket_name=bucket_name)
    blob = bucket.blob(dest_path)
    blob.upload_from_filename(source_file)
    return f"gs://{bucket_name}/{dest_path}"


def download_json_from_gcs(bucket_name: str, object_path: str) -> Any:
    """Download JSON object from GCS and decode it."""
    _, bucket = get_storage_bucket(bucket_name=bucket_name)
    blob = bucket.blob(object_path)
    return json.loads(blob.download_as_text())


def ensure_bq_dataset(bq_client: bigquery.Client, dataset_id: str) -> None:
    """Ensure BigQuery dataset exists."""
    try:
        bq_client.get_dataset(dataset_id)
    except Exception:
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = os.getenv("BQ_LOCATION", "asia-southeast1")
        bq_client.create_dataset(dataset)
        print(f"Created BigQuery dataset {dataset_id}")


def _is_missing(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _json_ready_value(value: Any) -> Any:
    if _is_missing(value):
        return None

    if isinstance(value, (list, dict, tuple, set)):
        return json.dumps(value, ensure_ascii=False)

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().isoformat()

    if hasattr(value, "isoformat") and not isinstance(value, (str, bytes)):
        try:
            return value.isoformat()
        except Exception:
            pass

    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except Exception:
            pass

    return value


def _infer_bq_type(series: pd.Series) -> str:
    if pdt.is_bool_dtype(series):
        return "BOOL"
    if pdt.is_integer_dtype(series):
        return "INT64"
    if pdt.is_float_dtype(series):
        return "FLOAT64"
    if pdt.is_datetime64_any_dtype(series):
        return "TIMESTAMP"
    return "STRING"


def _build_load_schema(bq_client: bigquery.Client, table_id: str, df: pd.DataFrame) -> list[bigquery.SchemaField]:
    try:
        table = bq_client.get_table(table_id)
        existing_schema = list(table.schema)
        existing_fields = {field.name for field in existing_schema}
    except NotFound:
        existing_schema = []
        existing_fields = set()

    schema = list(existing_schema)
    for column in df.columns:
        if column not in existing_fields:
            schema.append(bigquery.SchemaField(column, _infer_bq_type(df[column]), mode="NULLABLE"))

    return schema


def _build_raw_schema(bq_client: bigquery.Client, table_id: str, df: pd.DataFrame) -> list[bigquery.SchemaField]:
    try:
        table = bq_client.get_table(table_id)
        existing_schema = list(table.schema)
        existing_fields = {field.name for field in existing_schema}
    except NotFound:
        existing_schema = []
        existing_fields = set()

    schema = list(existing_schema)
    for column in df.columns:
        if column not in existing_fields:
            schema.append(bigquery.SchemaField(column, "STRING", mode="NULLABLE"))

    return schema


def _coerce_for_schema(df: pd.DataFrame, schema: list[bigquery.SchemaField]) -> pd.DataFrame:
    prepared = df.copy()
    for field in schema:
        if field.name not in prepared.columns:
            continue

        if field.field_type == "BOOL":
            def _to_bool(value):
                if _is_missing(value):
                    return None
                if isinstance(value, bool):
                    return value
                s = str(value).strip().lower()
                if s in {"true", "1", "yes", "y", "t"}:
                    return True
                if s in {"false", "0", "no", "n", "f"}:
                    return False
                return None

            prepared[field.name] = prepared[field.name].map(_to_bool)
        elif field.field_type == "INT64":
            def _to_int(value):
                if _is_missing(value):
                    return None
                if isinstance(value, int):
                    return int(value)
                try:
                    return int(float(value))
                except Exception:
                    return None

            prepared[field.name] = prepared[field.name].map(_to_int)
        elif field.field_type in {"FLOAT64", "NUMERIC", "BIGNUMERIC"}:
            def _to_float(value):
                if _is_missing(value):
                    return None
                try:
                    return float(value)
                except Exception:
                    return None

            prepared[field.name] = prepared[field.name].map(_to_float)
        elif field.field_type in {"TIMESTAMP", "DATETIME"}:
            prepared[field.name] = prepared[field.name].map(_json_ready_value)
        else:
            prepared[field.name] = prepared[field.name].map(_json_ready_value)

    return prepared


def coerce_df_to_bq_schema(df: pd.DataFrame, schema: list[bigquery.SchemaField]) -> pd.DataFrame:
    """Public wrapper for schema-driven dataframe coercion."""
    return _coerce_for_schema(df, schema)


def load_df_to_bq(bq_client: bigquery.Client, df: pd.DataFrame, table_id: str) -> None:
    """Load a DataFrame into BigQuery using JSON rows and schema-aware appends."""
    if df.empty:
        print(f"No rows to load into {table_id}")
        return

    schema = _build_load_schema(bq_client, table_id, df)
    prepared = _coerce_for_schema(df, schema)
    rows = prepared.to_dict(orient="records")

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        autodetect=False,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job_config.schema_update_options = [bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION]

    load_job = bq_client.load_table_from_json(rows, table_id, job_config=job_config)
    load_job.result()
    table = bq_client.get_table(table_id)
    print(f"Loaded {table.num_rows} rows into {table_id}")


def load_csv_to_bq(
    bq_client: bigquery.Client,
    gcs_uri: str,
    table_id: str,
    df: pd.DataFrame | None = None,
    columns: list[str] | None = None,
) -> None:
    """Load CSV from GCS into BigQuery as a raw staging table."""
    if df is None:
        if columns is None:
            df = pd.DataFrame()
        else:
            df = pd.DataFrame(columns=columns)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=False,
        allow_quoted_newlines=True,
        allow_jagged_rows=False,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job_config.schema = _build_raw_schema(bq_client, table_id, df)
    job_config.schema_update_options = [bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION]

    load_job = bq_client.load_table_from_uri(gcs_uri, table_id, job_config=job_config)
    load_job.result()
    table = bq_client.get_table(table_id)
    print(f"Loaded {table.num_rows} rows into {table_id}")


def sanitize_bq_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Sanitize DataFrame column names for BigQuery compatibility."""
    renamed = []
    seen = {}
    for col in df.columns:
        clean = re.sub(r"[^A-Za-z0-9_]", "_", str(col))
        clean = re.sub(r"_+", "_", clean).strip("_")
        if not clean:
            clean = "col"
        if clean[0].isdigit():
            clean = f"col_{clean}"
        count = seen.get(clean, 0)
        seen[clean] = count + 1
        if count:
            clean = f"{clean}_{count}"
        renamed.append(clean)

    df = df.copy()
    df.columns = renamed
    return df
