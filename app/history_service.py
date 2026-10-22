from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from app.database import AnalysisHistory

def save_analysis_history(
        db:Session,
        dataset_id: str,
        analysis_type:str,
        request_data:dict,
        result_data:dict,
        question: str|None=None
)->AnalysisHistory:
    history = AnalysisHistory(
        dataset_id=dataset_id,
        analysis_type=analysis_type,
        question=question,
        request_data=jsonable_encoder(request_data),
        result_data=jsonable_encoder(result_data),
    )

    db.add(history)
    db.commit()
    db.refresh(history)

    return history
