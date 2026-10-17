import pandas as pd

ALLOWED_AGGREGATION={
    "sum",
    "mean",
    "count",
    "min",
    "max"
}

def analyze_dataset(
        df: pd.DataFrame,
        group_by:str,
        metric:str,
        aggregation:str = "sum",
        descending:bool = True,
        limit:int=10
):
    if aggregation not in ALLOWED_AGGREGATION:
        raise ValueError("unsupported aggregation")
    if not 1<=limit<=100:
        raise ValueError("Limust be between 1 and 100")

    if group_by not in df.columns:
        raise ValueError(f"colum not found :{group_by}")
    if metric not in df.columns:
        raise ValueError(f"Column not found: {metric}")

    if aggregation in {"sum", "mean"}:
        if not pd.api.types.is_numeric_dtype(df[metric]):
            raise ValueError(
                f"Column '{metric}' must contain numeric data."
            )
    result=(
        df.groupby(group_by,dropna=False)[metric]
        .agg(aggregation)
        .reset_index()
    )    

    result= result.sort_values(
        by=metric,
        ascending=not descending,
        na_position="last",
    )

    return {
        "group_by": group_by,
        "metric":metric,
        "aggregation": aggregation,
        "results":result.to_dict(orient="records")
    }