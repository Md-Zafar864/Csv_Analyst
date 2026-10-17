
import os
import uuid
import asyncio
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.csv_service import inspect_csv
from app.database import Dataset, SessionLocal
from app.csv_service import load_saved_dataset
from typing import Literal
from pydantic import BaseModel,Field
from app.analyse_engine import analyze_dataset
from app.llm_service import create_analysis_plan

app = FastAPI(
    title="AI CSV Analyst",
    description="Analyze CSV datasets using natural language.",
    version="0.2.0",
)

UPLOAD_DIR = Path("data/uploads")
MAX_FILE_SIZE = 10 * 1024 * 1024

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/")
def home():
    return {
        "message": "AI CSV Analyst API is running",
        "status": "healthy",
    }


@app.post("/datasets/upload")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a CSV file.",
        )

    file_bytes = bytearray()

    try:
        while True:
            chunk = await file.read(1024 * 1024)

            if not chunk:
                break

            file_bytes.extend(chunk)

            if len(file_bytes) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail="File size must not exceed 10 MB.",
                )

        if not file_bytes:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        result = await run_in_threadpool(
            inspect_csv, bytes(file_bytes)
        )

    except HTTPException:
        raise

    except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise HTTPException(
            status_code=400,
            detail="The CSV could not be parsed.",
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid or unsupported CSV file.",
        ) from exc

    finally:
        await file.close()

    dataset_id = str(uuid.uuid4())
    stored_path = UPLOAD_DIR / f"{dataset_id}.csv"

    try:
        await run_in_threadpool(
            stored_path.write_bytes, bytes(file_bytes)
        )

        db: Session = SessionLocal()

        try:
            dataset = Dataset(
                id=dataset_id,
                filename=Path(file.filename).name,
                stored_path=str(stored_path),
                row_count=result["row_count"],
                column_count=result["column_count"],
                columns_info=result["columns"],
            )

            db.add(dataset)
            db.commit()

        finally:
            db.close()

    except Exception as exc:
        print("DATABASE ERROR:", repr(exc))

        if stored_path.exists():
            stored_path.unlink()

        raise HTTPException(
            status_code=500,
            detail="Could not save dataset metadata.",
        ) from exc

    return {
        "message": "Dataset uploaded successfully.",
        "dataset_id": dataset_id,
        "filename": Path(file.filename).name,
        "row_count": result["row_count"],
        "column_count": result["column_count"],
        "columns": result["columns"],
        "preview": result["preview"],
    }


@app.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str):
    db = SessionLocal()

    try:
        dataset = db.get(Dataset, dataset_id)

        if dataset is None:
            raise HTTPException(
                status_code=404,
                detail="Dataset not found.",
            )

        return {
            "dataset_id": dataset.id,
            "filename": dataset.filename,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
            "columns": dataset.columns_info,
            "created_at": dataset.created_at,
        }

    finally:
        db.close()

@app.get("/datasets/{dataset_id}/inspect")
def inspect_saved_dataset(dataset_id: str):
    db=SessionLocal()

    try:
        dataset=db.get(Dataset,dataset_id)

        if dataset is None:
            raise HTTPException(
                status_code=404,
                detail="Dataset not found",
            )
        try:
            df=load_saved_dataset(dataset.stored_path)

        except FileNotFoundError as exc:
             raise HTTPException(
                status_code=404,
                detail="Dataset file is missing from storage.",
            ) from exc    
        except (ValueError, pd.errors.ParserError) as exc:
            raise HTTPException(
                status_code=400,
                detail="Stored dataset could not be read.",
            ) from exc

        return {
            "dataset_id": dataset.id,
            "filename": dataset.filename,
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": [
                {
                    "name": str(column),
                    "dtype": str(df[column].dtype),
                    "null_count": int(df[column].isna().sum()),
                    "unique_values": int(df[column].nunique()),
                }
                for column in df.columns
            ],
            "preview": df.head(5).fillna("").to_dict(
                orient="records"
            ),
            "numeric_summary": df.describe(
                include="number"
            ).fillna(0).to_dict(),
        }
    finally:
        db.close()

class AnalyseRequest(BaseModel):
    group_by:str
    metric:str
    aggregation: Literal["sum", "mean", "count", "min", "max"] = "sum"
    descending: bool = True
    limit: int = Field(default=10, ge=1, le=100) 

@app.post("/datasets/{dataset_id}/analyze")
def analyze_saved_dataset(
    dataset_id:str,
    request:AnalyseRequest,

):
    
    db=SessionLocal()

    try:
        dataset=db.get(Dataset,dataset_id)

        if dataset is None:
            raise HTTPException(
                status_code=404,
                detail="Dataset not found."
            )
        try:
            df=load_saved_dataset(dataset.stored_path)

            result=analyze_dataset(
                df=df,
                group_by=request.group_by,
                metric=request.metric,
                aggregation=request.aggregation,
                descending=request.descending,
                limit=request.limit

            )

            return{
                "dataset_id":dataset.id,
                "filename":dataset.filename,
                "analysis":result,
            }
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail="Dataset file is missing.",
            ) from exc

        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc
    finally:
        db.close() 

class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


@app.post("/datasets/{dataset_id}/ask")

async def ask_dataset(
    dataset_id: str,
    request: AskRequest,
):
    db=SessionLocal()

    try:
        dataset=db.get(Dataset,dataset_id)

        if dataset is None:
            raise HTTPException(
                status_code=404,
                detail="Dataset not found.",
            )
        try:
            df = await run_in_threadpool(
                load_saved_dataset,
                dataset.stored_path,
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail="Dataset file is missing.",
            ) from exc    
        try:
            plan = await run_in_threadpool(
                create_analysis_plan,
                request.question,
                dataset.columns_info,
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=500,
                detail="AI service configuration is missing.",
            ) from exc    
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="Could not generate an analysis plan.",
            ) from exc
        try:
            result= await run_in_threadpool(
                analyze_dataset,
                df=df,
                group_by=plan.group_by,
                metric=plan.metric,
                aggregation=plan.aggregation,
                descending=plan.descending,
                limit=plan.limit,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="The requested analysis is invalid.",
            ) from exc

        return{
            "dataset_id": dataset.id,
            "question": request.question,
            "analysis_plan": plan.model_dump(),
            "analysis": result,
        }
    finally:
        db.close()