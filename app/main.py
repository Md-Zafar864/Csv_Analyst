from fastapi import FastAPI,UploadFile,File,HTTPException
import pandas as pd
from fastapi.concurrency import run_in_threadpool
from app.csv_service import inspect_csv
app = FastAPI()

@app.get("/")
def fn():
    return {"title": "Fast API"}

@app.post("/upload")
async def upload_csv(file:UploadFile=File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Upload csv file"
        )

    try:
        file_bytes= await file.read()

        if not file_bytes:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty"
            )
        if len(file_bytes) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail="File size must not exceed 10 MB.",
            )
        result= await run_in_threadpool(inspect_csv,file_bytes)

        return {
            "filename": file.filename,
            "dataset" : result
        }
    except HTTPException:
        raise
    except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read csv {exc}"
        )from exc

    except Exception as exc:
        print("ERROR TYPE:", type(exc).__name__)
        print("ERROR MESSAGE:", str(exc))

        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {str(exc)}"
        ) from exc
    