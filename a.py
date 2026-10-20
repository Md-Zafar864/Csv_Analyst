import pandas as pd

t="7"
target = pd.to_numeric(t, error="coerce")
print(pd.isna(target))
