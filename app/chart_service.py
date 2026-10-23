from numbers import Number
import pandas as pd
SUPPORTED_CHART_TYPES={"bar","line","pie"}

def prepare_chart_data(
        analysis:dict,
        chart_type:str ="bar",
        title:str|None=None,
):
    if chart_type not in SUPPORTED_CHART_TYPES:
        raise ValueError(
            f"Unsupported chart type: {chart_type}"
        )
    result =analysis.get("results")
    if not isinstance(result, list) or not result:
        raise ValueError("No result available")
    group_by=analysis.get("group_by")

    if isinstance(group_by,list):
        if len(group_by) !=1:
            raise ValueError(
                "Charts currently support exactly one grouping column"
            )
        x_key=group_by[0]
    elif isinstance(group_by,str) and group_by:
        x_key=group_by
    else:
        raise ValueError("A valid grouping column is required")   

    y_key = analysis.get("metric")

    if not isinstance(y_key, str) or not y_key:
        raise ValueError("A valid numeric metric is required.")

    for row in result:
        if not isinstance(row, dict):
            raise ValueError("Each result must be an object.")

        if x_key not in row or y_key not in row:
            raise ValueError(
                "Results must contain the grouping column and metric."
            )

        value = row[y_key]

        if (
            not isinstance(value, Number)
            or isinstance(value, bool)
        ):
            raise ValueError(
                f"Metric '{y_key}' must contain numeric values."
            )

    chart_results = [dict(row) for row in result]

    if chart_type == "pie":
        values = [row[y_key] for row in chart_results]

        if any(value < 0 for value in values):
            raise ValueError(
                "Pie charts cannot represent negative values."
            )

        if sum(values) <= 0:
            raise ValueError(
                "Pie charts require a positive total."
            )

    if chart_type == "line":
        dates = pd.to_datetime(
            [row[x_key] for row in chart_results],
            errors="coerce",
        )

        if dates.isna().any():
            raise ValueError(
                "Line charts require date-based grouping."
            )

        chart_results = [
            row
            for _, row in sorted(
                zip(dates, chart_results),
                key=lambda item: item[0],
            )
        ]

    aggregation = analysis.get("aggregation", "value")

    return {
        "chart_type": chart_type,
        "x_key": x_key,
        "y_key": y_key,
        "title": title or f"{aggregation.title()} of {y_key} by {x_key}",
        "data": chart_results,
    }

