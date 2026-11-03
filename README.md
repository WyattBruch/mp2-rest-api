# MP2: Data Processing REST API

This project is a FastAPI application that lets a client upload CSV datasets, store them in memory, and validate and clean them using the reusable data pipeline modules from MP1. `GET /health` reports the API status and version, `POST /upload` accepts a CSV file and returns its metadata, `GET /datasets/{dataset_id}` returns up to `limit` rows of a stored dataset, and `POST /datasets/{dataset_id}/process` validates and cleans a dataset using a JSON configuration, then returns a cleaning report. Every request is logged with a unique request ID, status code, and duration, and the ID is returned in the `X-Request-ID` response header. Automated tests use pytest and FastAPI's TestClient.

## Running

    source venv/bin/activate
    python -m pip install -r requirements.txt
    python -m uvicorn main:app --reload    # docs at http://127.0.0.1:8000/docs
    python -m pytest tests -v
