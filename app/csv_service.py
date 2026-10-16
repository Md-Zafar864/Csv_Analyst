import io
import pandas as pd


def inspect_csv(file_bytes:bytes):
    df=pd.read_csv(io.BytesIO(file_bytes))
    if df.empty:
        raise ValueError("Csv Contain no data row")
    if len(df.columns)==0:
        raise ValueError("Csv have no column.")

    columns=[]

    for col in df.columns:
        columns.append({
            "name":str(col),
            "dtype":str(df[col].dtype),
            "null_count":int(df[col].isna().sum()),
            "unique_value":int(df[col].nunique())
        })

    return {
        "row_count":len(df),
        "column_count":len(df.columns),
        "columns":columns,
        "preview":df.head(5).fillna("").to_dict(orient="records"),
        "numeric_summary":df.describe(
            include="number"
        ).fillna(0).to_dict(),
    }    