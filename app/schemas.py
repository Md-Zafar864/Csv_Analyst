from typing import Literal
from pydantic import BaseModel, Field

class FilterCondition(BaseModel):
    column:str= Field(min_length=1)
    operator:Literal["eq","ne", "gt", "gte", "lt", "lte","contains"]
    value: str=Field(max_length=500)