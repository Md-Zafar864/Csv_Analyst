import pandas as pd
from app.schemas import FilterCondition
ALLOWED_AGGREGATION={
    "sum",
    "mean",
    "count",
    "min",
    "max"
}
def parse_date(series: pd.Series):
    parsed = pd.to_datetime(series, errors="coerce")

    non_empty= series.notna().sum()

    if non_empty == 0:
        return None
    valid_dates = parsed.notna().sum()
    valid_ratio = valid_dates/non_empty

    if valid_ratio >= 0.8:
        return parsed

    return None



def apply_filters(
    df: pd.DataFrame,
    filters: list[FilterCondition] | None = None,
) -> pd.DataFrame:

    filtered_df = df.copy()

    for condition in filters or []:
        column = condition.column
        operator = condition.operator
        value = condition.value

        if column not in filtered_df.columns:
            raise ValueError(f"Column not found: {column}")

        series = filtered_df[column]
        is_numeric = pd.api.types.is_numeric_dtype(series.dtype)

        if operator == "contains":
            if is_numeric:
                raise ValueError(
                    f"'contains' requires a text column: {column}"
                )

            mask = series.astype("string").str.contains(
                value,
                case=False,
                na=False,
                regex=False,
            )

        elif operator in {"eq", "ne", "gt", "gte", "lt", "lte"}:

            if is_numeric:
                target = pd.to_numeric(value, errors="coerce")

                if pd.isna(target):
                    raise ValueError(
                        f"Invalid numeric filter value: {value}"
                    )

                left = series

            else:
                parsed_dates = parse_date(series)
                target_date = pd.to_datetime(
                    value,
                    errors="coerce",
                )

                if parsed_dates is not None and not pd.isna(target_date):
                    left = parsed_dates
                    target = target_date
                else:
                    left = series.astype("string").str.casefold()
                    target = value.casefold()

                    if operator not in {"eq", "ne"}:
                        raise ValueError(
                            f"'{operator}' requires a numeric or date column."
                        )

            if operator == "eq":
                mask = left == target
            elif operator == "ne":
                mask = left.notna() & (left != target)
            elif operator == "gt":
                mask = left > target
            elif operator == "gte":
                mask = left >= target
            elif operator == "lt":
                mask = left < target
            else:
                mask = left <= target

        else:
            raise ValueError(f"Unsupported filter operator: {operator}")

        filtered_df = filtered_df.loc[mask.fillna(False)]

    return filtered_df




def analyze_dataset(
    df: pd.DataFrame,
    group_by: str | list[str],
    metric: str,
    aggregation: str = "sum",
    descending: bool = True,
    limit: int = 10,
    filters: list[FilterCondition] | None = None,
):
    if aggregation not in ALLOWED_AGGREGATION:
        raise ValueError("Unsupported aggregation")

    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100")

    group_columns = (
        [group_by] if isinstance(group_by, str) else group_by
    )

    if not group_columns:
        raise ValueError("At least one grouping column is required.")

    if len(group_columns) > 3:
        raise ValueError("A maximum of 3 grouping columns is allowed.")

    if len(set(group_columns)) != len(group_columns):
        raise ValueError("Duplicate grouping columns are not allowed.")

    for column in group_columns:
        if column not in df.columns:
            raise ValueError(f"Column not found: {column}")

    if metric in group_columns:
        raise ValueError("The metric cannot also be a grouping column.")

    if metric not in df.columns:
        raise ValueError(f"Column not found: {metric}")

    if aggregation in {"sum", "mean"}:
        if not pd.api.types.is_numeric_dtype(df[metric]):
            raise ValueError(
                f"Column '{metric}' must contain numeric data."
            )

    filtered_df = apply_filters(df, filters)
    # Total rows in the original dataset
    rows_before_filtering = len(df)

# Rows remaining after filters
    rows_after_filtering = len(filtered_df)

    result = (
        filtered_df.groupby(group_columns, dropna=False)[metric]
        .agg(aggregation)
        .reset_index()
    )

    result = result.sort_values(
        by=metric,
        ascending=not descending,
        na_position="last",
    )

    result = result.head(limit)
    evidence = {
    "rows_before_filtering": rows_before_filtering,
    "rows_after_filtering": rows_after_filtering,
    "rows_excluded": rows_before_filtering - rows_after_filtering,

    "grouping_columns": group_columns,
    "metric": metric,
    "aggregation": aggregation,

    "filters": [
        condition.model_dump()
        for condition in filters or []
    ],

    "returned_group_count": len(result),

    "result_rows": result.to_dict(orient="records"),
}

    return {
        "group_by": (
            group_columns[0]
            if len(group_columns) == 1
            else group_columns
        ),
        "metric": metric,
        "aggregation": aggregation,
        "results": result.to_dict(orient="records"),
        "evidence":evidence,
    }