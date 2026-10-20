import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import Literal
from app.schemas import FilterCondition
load_dotenv()


class AnalysisPlan(BaseModel):
    group_by: str = Field(
        description="Existing colum used to group rows"
    )
    metric: str = Field(
        description="Existing column to aggregate."
    )
    aggregation: Literal[
        "sum", "mean", "count", "min", "max"
    ]
    
    descending: bool = True
    limit: int = Field(default=10, ge=1, le=100)
    filters: list[FilterCondition] = Field(default_factory=list)


def create_analysis_plan(question: str, columns_info: list):
    api_key=os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL")

    if not api_key or not model:
        raise RuntimeError("Gemini configuration is missing.")

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are an analysis planner for a CSV analytics application.

Your task is to convert the user's question into an analysis plan.

Available columns and their metadata:
{columns_info}

User question:
{question}

Rules:
1. Use only column names that exist in the provided schema.
2. Choose one grouping column and one metric column.
3. Choose only a supported aggregation.
4. Use sum for total revenue or total returns.
5. Use mean for average-value questions.
6. Use descending=true when the user asks for the highest,
   most, or largest result.
7. Never invent data or column names.
8. Return only a plan matching the required output schema.
9. If the question cannot be answered with this analysis
   plan, do not invent a plausible alternative.
10. Use filters when the question specifies a condition,
    such as a month, category, or numeric threshold.
11. Each filter must use an existing column.
12. Allowed filter operators are eq, ne, gt, gte, lt, lte, contains.
13. Use eq for exact matches, such as month equals March.
14. Use gt/gte/lt/lte for numeric comparisons.
15. Use contains for text substring matching.
16. Return an empty filters list when no filtering is needed.
17. Never create a filter that the supported operators cannot express.   
"""

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AnalysisPlan,
            temperature=0.1,
        ),
    )

    if not response.text:
        raise ValueError("The AI returned an empty response.")

    return AnalysisPlan.model_validate_json(response.text)