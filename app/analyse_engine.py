import pandas as pd
from app.schemas import FilterCondition
ALLOWED_AGGREGATION={
    "sum",
    "mean",
    "count",
    "min",
    "max"
}

def apply_filters(
        df:pd.DataFrame,
        filters:list[FilterCondition] | None=None,

)->pd.DataFrame:
    filtered_df=df.copy()
    for condition in filters or []:
        column=condition.column
        operator=condition.operator
        value=condition.value

        if column not in filtered_df.columns:
            raise ValueError(f"Column not found: {column}")
         
        series = filtered_df[column]
        is_numeric=pd.api.types.is_numeric_dtype(series.dtype)

        if operator == "contains":
            if is_numeric:
                raise ValueError(
                    f"'contains' requires a text column: {column}"
                )

            mask=series.astype("string").str.contains(
                value,
                case=False,
                na=False,
                regex=False,
            )

        elif operator in {"eq", "ne", "gt", "gte", "lt", "lte"}:

            if is_numeric:
                target=pd.to_numeric(value, error="coerce")

                if pd.isna(target):
                    raise ValueError(
                        f"Invalid numeric filter value: {value}"
                    )
                if operator == "eq":
                    mask = series == target
                elif operator == "ne":
                    mask = series.notna() & (series != target)
                elif operator == "gt":
                    mask = series > target
                elif operator == "gte":
                    mask = series >= target
                elif operator == "lt":
                    mask = series < target
                else:
                    mask = series <= target

            else:
                if operator not in {"eq", "ne"}:
                    raise ValueError(
                        f"'{operator}' requires a numeric column."
                    )

                normalized = series.astype("string").str.casefold()
                target = value.casefold()

                if operator == "eq":
                    mask = normalized == target
                else:
                    mask = series.notna() & (normalized != target)

        else:
            raise ValueError(f"Unsupported filter operator: {operator}")

        filtered_df = filtered_df.loc[mask.fillna(False)]

    return filtered_df





def analyze_dataset(
        df: pd.DataFrame,
        group_by:str,
        metric:str,
        aggregation:str = "sum",
        descending:bool = True,
        limit:int=10,
        filters: list[FilterCondition] | None = None,
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
    filtered_df = apply_filters(df, filters)

    result = (
    filtered_df.groupby(group_by, dropna=False)[metric]
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