import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point
import matplotlib.pyplot as plt
from shapely.geometry import LineString
import contextily as ctx
import os


data_file = "Substation/data_Pandapower.xlsx"  # network definition
line_stats_file = "results/line_statsB.csv"  # simulation results
subs_file = "substation/Substations2.csv"
subs4_file = "Substation/Substations3 110.csv"
subs6_file = "Substation/Substation3 220.csv"
subs8_file = "Substation/Substations3 380.csv"

bus_geo = pd.read_excel(data_file, sheet_name="bus_geodata")
for col in ["x", "y"]:
    if col in bus_geo.columns:
        bus_geo[col] = (
            bus_geo[col]
            .astype(str)
            .str.replace(",", ".")
            .str.replace(";", "")
            .str.strip()
        )
        bus_geo[col] = pd.to_numeric(bus_geo[col], errors="coerce")


# Load line infomation
line_data = pd.read_excel(data_file, sheet_name="line")
line_data.columns = line_data.columns.str.strip()

line_stats = pd.read_csv(line_stats_file)
line_stats.columns = line_stats.columns.str.strip()


# create line geodata from bus Coordinates
def get_bus_coord(bus_idx):

    # Return (x, y) tuple for a given bus index.

    if bus_idx in bus_geo.index:
        row = bus_geo.loc[bus_idx]
        return (row["x"], row["y"])
    elif "bus" in bus_geo.columns:
        row = bus_geo[bus_geo["bus"] == bus_idx]
        if not row.empty:
            return (row.iloc[0]["x"], row.iloc[0]["y"])
    return None


line_geodata = []
for i, row in line_data.iterrows():
    from_coord = get_bus_coord(row["from_bus"])
    to_coord = get_bus_coord(row["to_bus"])
    if from_coord and to_coord:
        line_geodata.append(
            {
                "index": 1,
                "from_bus": row["from_bus"],
                "to_bus": row["to_bus"],
                "geometry": LineString((from_coord, to_coord)),
            }
        )

griddf_lines = gpd.GeoDataFrame(line_geodata, geometry="geometry", crs="EPSG:4326")


if len(line_stats) == len(griddf_lines):
    griddf_lines = pd.concat([griddf_lines, line_stats], axis=1)
else:
    griddf_lines = griddf_lines.merge(
        line_stats, left_on="index", right_index=True, how="left"
    )


# load substation1 points and convert to GeodataFrame
def load_substation1_csv(file_path):
    subs_df = pd.read_csv(file_path)

    subs_df["geometry"] = subs_df.apply(
        lambda x: Point(x["Longitude"], x["Latitude"]), axis=1
    )
    grid_subs = gpd.GeoDataFrame(subs_df, geometry="geometry", crs="EPSG:4326")
    return grid_subs


grid_subs_df = load_substation1_csv(subs_file)


# load substations2 lines and convert to GeoDataFrame
def load_substation2_csv(path, color):
    if os.path.exists(path):
        df = pd.read_csv(path)
        df.columns = df.columns.str.strip()
        if {"lon", "lat"}.issubset(df.columns):
            griddf_lines = gpd.GeoDataFrame(
                df, geometry=gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326"
            )
            griddf_lines["color"] = color
            return griddf_lines
    return None


griddf_lines_sub4 = load_substation2_csv(subs4_file, "blue")
griddf_lines_sub6 = load_substation2_csv(subs6_file, "green")
griddf_lines_sub8 = load_substation2_csv(subs8_file, "red")


# convert both points and lines CRS for OpenStreetMap
grid_subs_pts = grid_subs_df.to_crs(epsg=3857)

griddf_lines = griddf_lines.to_crs(epsg=3857)

if griddf_lines_sub4 is not None:
    griddf_lines_sub4 = griddf_lines_sub4.to_crs(epgs=3857)
if griddf_lines_sub6 is not None:
    griddf_lines_sub6 = griddf_lines_sub6.to_crs(epsg=3857)
if griddf_lines_sub8 is not None:
    griddf_lines_sub8 = griddf_lines_sub8.to_crs(epgs=3857)


# plot lines on heatmap
fig, ax = plt.subplots(figsize=(12, 10))

if "mean_loading%" in griddf_lines.columns:
    griddf_lines.plot(
        column="mean_loading%",
        cmap="YlOrRd",
        linewidth=3,
        legend=True,
        legend_kwds={"label": "Mean Line Loading (%)"},
        ax=ax,
        alpha=0.8,
        missing_kwds={"color": "lightgrey", "label": "No data"},
    )
else:
    griddf_lines.plot(ax=ax, color="grey", linewidth=1.5, label="No stats")

# plot substation points on heatmap
grid_subs_pts.plot(
    ax=ax,
    column="Voltage_ADJ",
    cmap="cool",
    markersize=50,
    edgecolor="black",
    alpha=0.5,
    legend=False,
)
# Add labels
for idx, row in grid_subs_pts.iterrows():
    ax.text(row.geometry.x + 800, row.geometry.y + 800, row["Name"], fontsize=7)


# plot substations
if griddf_lines_sub4 is not None:
    griddf_lines_sub4.plot(
        ax=ax, color="blue", markersize=60, alpha=0.8, label="Substations 110 KV"
    )
if griddf_lines_sub6 is not None:
    griddf_lines_sub6.plot(
        ax=ax, color="green", markersize=60, alpha=0.8, label="Substation 220 KV"
    )
if griddf_lines_sub8 is not None:
    griddf_lines_sub8.plot(
        ax=ax, color="red", markersize=60, alpha=0.8, label="Substations 380 KV"
    )

# Add openstreet map
ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)

# Style
ax.set_title("Grid Line Loading Heatmap (Mean Loading % on OSM)", fontsize=14)
ax.set_axis_off()
plt.legend()
plt.tight_layout()


# Save and show
os.makedirs
output_file = "results/line_loading_heatmao_osm.png"
# plt.savefig(output_file, dpi=300, bbox_inches="tight")
plt.show()

# print(f" heatmap saved to: {output_file}")
