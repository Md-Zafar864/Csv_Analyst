
import os
import uuid
import asyncio
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder
from app.csv_service import inspect_csv
from app.database import Dataset, SessionLocal
from app.database import get_db, AnalysisHistory,SavedQuery
from app.csv_service import load_saved_dataset
from typing import Literal
from pydantic import BaseModel,Field
from app.analyse_engine import analyze_dataset
from app.llm_service import create_analysis_plan
from app.history_service import save_analysis_history
from app.schemas import FilterCondition,SavedQueryCreate
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
    group_by:list[str] = Field(min_length=1)
    metric:str
    aggregation: Literal["sum", "mean", "count", "min", "max"] = "sum"
    descending: bool = True
    limit: int = Field(default=10, ge=1, le=100)
    filters: list[FilterCondition] = Field(default_factory=list) 

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
                limit=request.limit,
                filters=request.filters

            )
            save_analysis_history(
                db=db,
                dataset_id=dataset_id,
                analysis_type="manual",
                request_data=request.model_dump(),
                result_data=result,
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
                filters=plan.filters,
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

@app.get("/datasets/{dataset_id}/history")
def get_dataset_history(
    dataset_id: str,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    if skip < 0:
        raise HTTPException(
            status_code=400,
            detail="skip cannot be negative.",
        )

    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 100.",
        )

    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id)
        .first()
    )

    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found.",
        )

    query = db.query(AnalysisHistory).filter(
        AnalysisHistory.dataset_id == dataset_id
    )

    total = query.count()

    records = (
        query
        .order_by(AnalysisHistory.created_at.desc(),
                  AnalysisHistory.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return {
        "dataset_id": dataset_id,
        "total": total,
        "skip": skip,
        "limit": limit,
        "count": len(records),
        "history": [
            {
                "id": record.id,
                "question": record.question,
                "analysis_type": record.analysis_type,
                "created_at": record.created_at,
            }
            for record in records
        ],
    }

@app.post("/datasets/{dataset_id}/saved-query")
def create_saved_query(
    dataset_id: str,
    request: SavedQueryCreate,
    db: Session = Depends(get_db),
):
    print("STEP 1: Endpoint called", flush=True)

    try:
        dataset = db.query(Dataset).filter(
            Dataset.id == dataset_id
        ).first()

        print("STEP 2: Dataset checked", flush=True)

        if dataset is None:
            raise HTTPException(
                status_code=404,
                detail="Dataset not found."
            )

        query_data = jsonable_encoder(request.query_data)

        print("STEP 3: Query data prepared", flush=True)

        saved_query = SavedQuery(
            dataset_id=dataset_id,
            name=request.name.strip(),
            query_data=query_data,
        )

        print("STEP 4: SavedQuery object created", flush=True)

        if not saved_query.name:
            raise HTTPException(
                status_code=422,
                detail="Query name cannot be blank."
            )

        db.add(saved_query)
        print("STEP 5: Added to session", flush=True)

        db.commit()
        print("STEP 6: Committed", flush=True)

        db.refresh(saved_query)
        print("STEP 7: Refreshed", flush=True)

        return {
            "message": "Query saved successfully.",
            "saved_query": {
                "id": saved_query.id,
                "dataset_id": saved_query.dataset_id,
                "name": saved_query.name,
                "query_data": saved_query.query_data,
                "created_at": saved_query.created_at,
            },
        }

    except HTTPException:
        raise

    except Exception as exc:
        db.rollback()
        print("ACTUAL ERROR:", repr(exc), flush=True)
        raise

@app.get("/datasets/{dataset_id}/saved-queries")
def list_saved_queries(
        dataset_id:str,
        db:Session=Depends(get_db)
    ):
        dataset=(
            db.query(Dataset)
            .filter(dataset_id==dataset_id)
            .first()
        )
        if dataset is None:
            raise HTTPException(
                status_code=404,
                detail="Dataset not found"
            )

        queries = (
        db.query(SavedQuery)
        .filter(SavedQuery.dataset_id == dataset_id)
        .order_by(SavedQuery.created_at.desc(), SavedQuery.id.desc())
        .all()
    )

        return {
            "dataset_id": dataset_id,
            "count": len(queries),
            "saved_queries": [
                {
                    "id": query.id,
                    "name": query.name,
                    "created_at": query.created_at,
                }
                for query in queries
            ],
        }

@app.get("/saved-queries/{query_id}")
def get_saved_query(
    query_id:int,
    db: Session=Depends(get_db)
):
    query=(db.query(SavedQuery).filter(SavedQuery.id==query_id).first())

    if query is None:
        raise HTTPException(
            status_code=404,
            detail= "Saved query not found"
        )
    return{
        "id": query.id,
        "dataset_id": query.dataset_id,
        "name": query.name,
        "query_data": query.query_data,
        "created_at": query.created_at,
    }


