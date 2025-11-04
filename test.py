import pandas as pd

load = pd.read_csv("timeseriesdata/conventionLoad_data.csv")
pv = pd.read_csv("timeseriesdata/photovoltaic_data.csv")

diff = pv.iloc[:, 0] - load.iloc[:, 0]
print("Timesteps with PV > Load:", (diff > 0).sum(), "of", len(diff))