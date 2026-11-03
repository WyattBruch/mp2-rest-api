import io
import json
import logging
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from data_pipeline import create_cleaning_report, process_data, validate_dataframe
from src import (
    DatasetInfo,
    DatasetStorage,
    HealthResponse,
    ProcessConfig,
    ProcessingReport,
    log_requests,
    setup_logging,
)

setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Data Processing API", version="1.0.0")
app.middleware("http")(log_requests)
storage = DatasetStorage()


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return the application status and version."""
    return HealthResponse(status="ok", version=app.version)


@app.post("/upload", response_model=DatasetInfo)
async def upload_dataset(file: UploadFile = File(...)):
    """Read and store a CSV upload."""
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix != ".csv":
        logger.warning(f"Unsupported file format: {suffix or '(no extension)'}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{suffix}'. Only .csv files are accepted.",
        )

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as e:
        logger.warning(f"Could not read CSV {filename}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Could not read CSV file: {e}",
        ) from e

    dataset_id = storage.save(df, filename)
    logger.info(f"Uploaded dataset: id={dataset_id}, filename={filename}, rows={len(df)}")
    return DatasetInfo(**storage.get_metadata(dataset_id))


@app.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: int, limit: int = Query(default=100, ge=1)):
    """Return up to limit rows from a stored dataset."""
    df = storage.get(dataset_id)
    if df is None:
        logger.warning(f"Dataset not found: {dataset_id}")
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    records = json.loads(df.head(limit).to_json(orient="records"))
    logger.info(f"Retrieved dataset: id={dataset_id}, returned_rows={len(records)}")
    return {"id": dataset_id, "data": records, "total_rows": len(df)}

@app.post(
    "/datasets/{dataset_id}/process",
    response_model=ProcessingReport
)
def process_dataset(dataset_id: int, config: ProcessConfig):
    """Validate and process a stored dataset using MP1 functions."""
    df = storage.get(dataset_id)
    if df is None:
        logger.warning(f"Dataset not found: {dataset_id}")
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    config_dict = config.model_dump()
    required_columns = config_dict["validation"]["required_columns"]
    numeric_columns = config_dict["validation"]["numeric_columns"]

    missing_numeric = [col for col in numeric_columns if col not in df.columns]
    if missing_numeric:
        logger.warning(f"Numeric columns not in dataset {dataset_id}: {missing_numeric}")
        raise HTTPException(
            status_code=400,
            detail=f"Numeric column(s) not found in dataset: {', '.join(missing_numeric)}",
        )

    try:
        rows_before_validation = len(df)
        validated = validate_dataframe(df, required_columns, numeric_columns)
        validation_rows_removed = rows_before_validation - len(validated)
        logger.info(
            f"Validated dataset: id={dataset_id}, "
            f"rows={rows_before_validation} → {len(validated)}"
        )

        df_before = validated.copy()
        processed = process_data(validated, config_dict)
        report = create_cleaning_report(df_before, processed)
    except ValueError as error:
        logger.warning(f"Processing failed for dataset {dataset_id}: {error}")
        raise HTTPException(status_code=400, detail=str(error)) from error

    storage.update(dataset_id, processed)
    logger.info(
        f"Processed dataset: id={dataset_id}, "
        f"validation_removed={validation_rows_removed}, "
        f"rows_before={report['rows_before']}, rows_after={report['rows_after']}"
    )
    return {
        "id": dataset_id,
        "validation_rows_removed": validation_rows_removed,
        "cleaning_report": report,
    }
