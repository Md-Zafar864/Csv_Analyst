# http://127.0.0.1:8001
# python -m uvicorn app.main:app --reload --port 8001

from app.chart_service import prepare_chart_data


analysis = {
    "group_by": "category",
    "metric": "revenue",
    "aggregation": "sum",
    "results": [
        {"category": "Electronics", "revenue": 423000},
        {"category": "Furniture", "revenue": 131000},
    ],
}

chart = prepare_chart_data(analysis)

print(chart)