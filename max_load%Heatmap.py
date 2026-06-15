import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point
from bokeh.io import output_file, show, save
from bokeh.plotting import figure
from bokeh.models import (
    ColumnDataSource,
    HoverTool,
    LinearColorMapper,
    ColorBar,
    BasicTicker,
    PrintfTickFormatter,
)
from bokeh.models import WMTSTileSource
from bokeh.palettes import YlOrRd9, Category10
import numpy as np
import os


data_file = "Substation/data_Pandapower.xlsx"  # network definition
line_stats_file = "results/line_stats.csv"  # simulation results
subs_file = "substation/Substations2.csv"
subs4_line_file = "Substation/Substations3 110.csv"
subs6_line_file = "Substation/Substations3 220.csv"
subs8_line_file = "Substation/Substations3 380.csv"


# clean coordinate
def clean_coordinates(df):
    for col in df.columns:
        if any(k in col.lower() for k in ["lon", "lat", "x", "y"]):
            df[col] = df[col].astype(str).str.replace(",", ".").str.strip()
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# web_marcator converts
def web_mercator(lon, lat):
    k = 6378137
    lon, lat = pd.to_numeric(lon, errors="coerce"), pd.to_numeric(lat, errors="coerce")
    x = lon * (np.pi / 180) * k
    y = np.log(np.tan((90 + lat) * np.pi / 360.0)) * k
    return x, y


# Load base and line infomation
bus_geo = pd.read_excel(data_file, sheet_name="bus_geodata")
bus_geo = clean_coordinates(bus_geo)

line_data = pd.read_excel(data_file, sheet_name="line")
line_data.columns = line_data.columns.str.strip()

line_stats = pd.read_csv(line_stats_file)
line_stats.columns = line_stats.columns.str.strip()


# create line geodata from bus Coordinates
def get_bus_coord(bus_idx):

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
                "index": i,
                "from_bus": row["from_bus"],
                "to_bus": row["to_bus"],
                "geometry": LineString([from_coord, to_coord]),
            }
        )

griddf_lines = gpd.GeoDataFrame(line_geodata, geometry="geometry", crs="EPSG:4326")

# link line_stats using index (mean_loading%)
if len(line_stats) == len(griddf_lines):
    griddf_lines = pd.concat([griddf_lines, line_stats], axis=1)
else:
    griddf_lines = griddf_lines.merge(
        line_stats, left_on="index", right_index=True, how="left"
    )


# Extract coordinates (since Bokeh can't handle shapely geometries)
griddf_lines["x0"] = griddf_lines.geometry.apply(
    lambda g: g.coords[0][0] if g and not g.is_empty else np.nan
)
griddf_lines["y0"] = griddf_lines.geometry.apply(
    lambda g: g.coords[0][1] if g and not g.is_empty else np.nan
)
griddf_lines["x1"] = griddf_lines.geometry.apply(
    lambda g: g.coords[-1][0] if g and not g.is_empty else np.nan
)
griddf_lines["y1"] = griddf_lines.geometry.apply(
    lambda g: g.coords[-1][1] if g and not g.is_empty else np.nan
)

# Convert to Web Mercator for plotting
griddf_lines["x0"], griddf_lines["y0"] = web_mercator(
    griddf_lines["x0"], griddf_lines["y0"]
)
griddf_lines["x1"], griddf_lines["y1"] = web_mercator(
    griddf_lines["x1"], griddf_lines["y1"]
)


# Drop the geometry column before passing to ColumnDataSource
griddf_lines = griddf_lines.drop(columns=["geometry"], errors="ignore")


# load substations points
subs_point_df = pd.read_csv(subs_file)
subs_pt_df = clean_coordinates(subs_point_df)
subs_pt_df["x"], subs_pt_df["y"] = web_mercator(
    subs_pt_df["Longitude"], subs_pt_df["Latitude"]
)


# Load substation lines
def load_line_csv(file_path, voltage_label, color):
    df = pd.read_csv(file_path)
    df.columns = df.columns.str.strip()
    df = clean_coordinates(df)
    lon_cols = [c for c in df.columns if "lon" in c.lower() or "x" in c.lower()]
    lat_cols = [c for c in df.columns if "lat" in c.lower() or "y" in c.lower()]

    if len(lon_cols) < 2 or len(lat_cols) < 2:
        print(f"File {file_path} missing coordinate pairs — skipping.")
        return None
    x0, y0 = web_mercator(df[lon_cols[0]], df[lat_cols[0]])
    x1, y1 = web_mercator(df[lon_cols[1]], df[lat_cols[1]])
    df["x0"], df["y0"], df["x1"], df["y1"] = x0, y0, x1, y1
    df["voltage"] = voltage_label
    df["color"] = color
    return df


# lines_110 = load_line_csv(subs4_line_file, "110 kV", "blue")
# lines_220 = load_line_csv(subs6_line_file, "220 kV", "green")
# lines_380 = load_line_csv(subs8_line_file, "380 kV", "black")


#  Prepare ColumnDataSource
grid_lines = ColumnDataSource(griddf_lines)
grid_sub_main = ColumnDataSource(subs_pt_df)
# grid_sub110 = ColumnDataSource(lines_110) if lines_110 is not None else None
# grid_sub220 = ColumnDataSource(lines_220) if lines_220 is not None else None
# grid_sub380 = ColumnDataSource(lines_380) if lines_380 is not None else None


# set map figure
url = "https://tile.openstreetmap.de/{z}/{x}/{y}.png"
# attribution = "xyz.OpenStreetMap.Mapnik"
p = figure(
    x_axis_type="mercator",
    y_axis_type="mercator",
    title="Interactive Grid Max Line Loading and Substation Map",
    width=2000,
    height=1000,
    tools="pan,wheel_zoom,reset,save,hover",
)

p.add_tile(WMTSTileSource(url=url))
# p.add_tile(tile_provider)


# plot lines colored by mean loading%
if "max_loading%" in griddf_lines.columns:
    color_mapper = LinearColorMapper(
        palette=YlOrRd9[::-1],
        low=griddf_lines["max_loading%"].min(),
        high=griddf_lines["max_loading%"].max(),
    )

    p.segment(
        "x0",
        "y0",
        "x1",
        "y1",
        source=grid_lines,
        color={"field": "max_loading%", "transform": color_mapper},
        line_width=3,
        legend_label="Line Max Loading (%)",
    )
    color_bar = ColorBar(
        color_mapper=color_mapper,
        ticker=BasicTicker(desired_num_ticks=10),
        formatter=PrintfTickFormatter(format="%d%%"),
        label_standoff=12,
        width=8,
        location=(0, 0),
    )
    p.add_layout(color_bar, "right")

else:
    p.segment(
        "x0",
        "y0",
        "x1",
        "y1",
        source=grid_lines,
        color="gray",
        line_width=2,
        legend_label="Lines",
    )

# Hover tooltips
hover = HoverTool()
p.hover.tooltips = [
    ("Line index", "@index"),
    ("From bus", "@from_bus"),
    ("To bus", "@to_bus"),
    ("Max loading (%)", "@{max_loading%}{0.0}"),
]

# # create a color function
# def give_color(voltage):
#     if pd.isna(voltage):
#         return "gray"
#     try:
#         v = float(str(voltage).replace("KV", "").replace(",", ".").strip())
#     except:
#         v= 0
#     if v <= 120:
#         return "blue"
#     elif 120 < v <= 250:
#         return "green"
#     else:
#         return "black"


# subs_pt_df["color"] = subs_pt_df["Voltage_ADJ"].apply(give_color)

#   plot substation points
p.circle(
    x="x",
    y="y",
    size=10,
    color=Category10[10][0],
    alpha=0.8,
    source=grid_sub_main,
    legend_label="Substations",
)

# # Voltage-level connections
# for src, lbl in [(grid_sub110, "110 kV"), (grid_sub220, "220 kV"), (grid_sub380, "380 kV")]:
#     if src:
#         p.segment("x0", "y0", "x1", "y1", source=src, color=src.data["color"][0],
#                   line_width=2, legend_label=lbl)

# 10. Save and show
output_html = "results/interactive_grid_heatmap.html"
output_file(output_html)
show(p)
save(p)
