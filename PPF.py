import pandapower as pp
import pandas as pd
from pandapower.file_io import to_json
from pandapower import to_excel
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
from plotly.graph_objs import heatmap


# load
def load_excel_data(file_path, sheet_name, index_col=0, strip_columns=False):
    df = pd.read_excel(file_path, sheet_name=sheet_name, index_col=index_col)
    if strip_columns:
        df.columns = df.columns.str.strip()
    return df


#   net = pp.create_empty_network()

#   create network function

df_bus = pd.read_excel("Substation\data_Pandapower.xlsx", sheet_name="bus", index_col=0)
# strip column name to avoid issues with spaces
df_bus.columns = df_bus.columns.str.strip()


def create_buses(net, df_bus):
    for i, row in df_bus.iterrows():
        pp.create_bus(
            net,
            vn_kv=row["vn_kv"],
            name=row["name"],
            type=row.get("type", "b"),
            zone=row.get("zone", None),
            in_service=row.get("in_service", True),
        )
    print(net.bus)


def create_loads(net, df_load):
    for i in df_load.index:
        pp.create_load(net, **df_load.loc[i, :].to_dict())


def create_sgen(net, df_sgen):
    for i in df_sgen.index:
        pp.create_sgen(net, **df_sgen.loc[i, :].to_dict())
    print(net.sgen)


def create_ext_grid(net, df_ext_grid):
    for i in df_ext_grid.index:
        pp.create_ext_grid(net, **df_ext_grid.loc[i, :].to_dict())


def create_lines(net, df_lines):
    # create powerlines
    for _, row in df_lines.iterrows():
        # clean lenght_km column
        df_lines["length_km"] = (
            df_lines["length_km"].astype(str).str.replace(",", ".").astype(float)
        )
        length = float(str(row["length_km"]).replace(".", "").strip())

        pp.create_line_from_parameters(
            net,
            from_bus=int(row["from_bus"]),
            to_bus=int(row["to_bus"]),
            length_km=length,
            r_ohm_per_km=row["r_ohm_per_km"],
            x_ohm_per_km=row["x_ohm_per_km"],
            c_nf_per_km=row["c_nf_per_km"],
            g_us_per_km=row["g_us_per_km"],
            max_i_ka=row["max_i_ka"],
            name=row["name"],
            type=row["type"],
            df=row.get("df", 1),
            parallel=row.get("parallel", 1),
            in_service=row.get("in_service", True),
        )


def create_trafo(net, df_trafo):
    for _, row in df_trafo.iterrows():
        pp.create_transformer_from_parameters(
            net,
            hv_bus=int(row["hv_bus"]),
            lv_bus=int(row["lv_bus"]),
            sn_mva=row["sn_mva"],
            vn_hv_kv=row["vn_hv_kv"],
            vn_lv_kv=row["vn_lv_kv"],
            vk_percent=row["vk_percent"],
            vkr_percent=row["vkr_percent"],
            pfe_kw=row["pfe_kw"],
            i0_percent=row["i0_percent"],
            shift_degree=row["shift_degree"],
            tap_side=row["tap_side"],
            tap_neutral=row["tap_neutral"],
            tap_min=row["tap_min"],
            tap_max=row["tap_max"],
            tap_step_percent=row["tap_step_percent"],
            tap_step_degree=row["tap_step_degree"],
            tap_pos=row["tap_pos"],
            tap_phase_shifter=row["tap_phase_shifter"],
            parallel=row["parallel"],
            df=row["df"],
            in_service=row["in_service"],
            name=row["name"],
        )


def run_power_flow(net, result_file="results/Result.xlsx"):
    try:
        pp.runpp(net)
    except pp.LoadflowNotConverged:
        print("Power flow did not converge. Running diagnostic:")
        pp.diagnostic(net, detailed_report=True)

    # print result of PPF without battery to file
    to_excel(net, result_file)

    return net


# overload detection
def get_overload_rows(
    result_file, threshold=70, overload_file="overload_lines/overload_line.xlsx"
):
    # load result and compare with treshold
    df_res_line = pd.read_excel(result_file, sheet_name="res_line")
    overload_rows = df_res_line[df_res_line["loading_percent"] > threshold]

    if not overload_rows.empty:
        overload_rows.to_excel(overload_file, index=False)
        print(f"Overloads detected and saved to {overload_file}")
    else:
        print("No overloads detected.")

    return overload_rows


def get_overload_rows2(
    result_file, threshold=70, overload_file="overload_lines/overload_line2.xlsx"
):
    # load result and compare with treshold
    df_res_line = pd.read_excel(result_file, sheet_name="res_line")
    overload_rows = df_res_line[df_res_line["loading_percent"] > threshold]

    if not overload_rows.empty:
        overload_rows.to_excel(overload_file, index=False)
        print(f"Overloads detected and saved to {overload_file}")
    else:
        print("No overloads detected.")

    return overload_rows


# Get the overload lines
def battery_discharge(net, overload_rows, base_path, discharge_mw=70):
    if overload_rows.empty:
        return

    df_line_overload = pd.read_excel(base_path, sheet_name="line")
    overload_line = df_line_overload.loc[overload_rows.index]

    to_bus = overload_line["to_bus"]
    for b in to_bus:
        pp.create_load(net, bus=b, p_mw=-70, q_mvar=0.0, name=f"BatteryFeed_inline_{b}")

    print(f"Battery dispatch at bus {to_bus} with {discharge_mw} MW injection")


# Build a heatmap the whole dataset


def plot_loading_percent_heatmap(
    file1, file2, label1, label2, sheet_name="res_line", threshold=70
):

    df1 = pd.read_excel(file1, sheet_name="res_line")
    df2 = pd.read_excel(file2, sheet_name="res_line")

    # Reshape into one row with each column representing a line index
    heatmap_data = pd.DataFrame(
        [df1["loading_percent"].values, df2["loading_percent"].values],
        index=[label1, label2],
        columns=[f" Line {i}" for i in df1.index],
    )

    # create tresholdmask for overloads
    overload_mask = heatmap_data > threshold

    # plot heatmap
    plt.figure(figsize=(12, 4))
    ax1 = sns.heatmap(
        heatmap_data,
        annot=True,
        cmap="coolwarm",
        fmt=".1f",
        cbar_kws={"label": "Loading Percent (%)"},
        linewidths=0.5,
        linecolor="gray",
    )

    # Highlight Overload Cells
    for y in range(heatmap_data.shape[0]):
        for x in range(heatmap_data.shape[1]):
            if overload_mask.iloc[y, x]:
                ax1.add_patch(
                    plt.Rectangle((x, y), 1, 1, fill=False, edgecolor="black", lw=2)
                )

    plt.title(f"Line Loading Comparison (Overload > {threshold}%)", fontsize=12)
    plt.xlabel("Line Index")
    plt.ylabel("")
    plt.tight_layout()
    plt.show()


# Build heatmap for OVerload_lines


def plot_Overload_lines_heatmap(
    file1, file2, overload_rows, label1, label2, sheet_name="Sheet", threshold=70
):
    if overload_rows.empty:
        print("No overloaded lines to plot.")
        return

    df1 = pd.read_excel(file1, sheet_name="res_line")
    df2 = pd.read_excel(file2, sheet_name="res_line")

    df_overload1 = df1.loc[overload_rows.index]
    df_overload2 = df2.loc[overload_rows.index]

    # Reshape into one row with each column representing a line index
    heatmap_data_2 = pd.DataFrame(
        [
            df_overload1["loading_percent"].values,
            df_overload2["loading_percent"].values,
        ],
        index=[label1, label2],
        columns=[f" Line {i}" for i in df_overload1.index],
    )

    # create tresholdmask for overloads
    overload_mask_1 = heatmap_data_2 > threshold

    # plot heatmap
    plt.figure(figsize=(12, 4))
    ax = sns.heatmap(
        heatmap_data_2,
        annot=True,
        cmap="coolwarm",
        fmt=".1f",
        cbar_kws={"label": "Loading Percent (%)"},
        linewidths=0.5,
        linecolor="gray",
    )

    # Highlight Overload Cells
    for y in range(heatmap_data_2.shape[0]):
        for x in range(heatmap_data_2.shape[1]):
            if overload_mask_1.iloc[y, x]:
                ax.add_patch(
                    plt.Rectangle((x, y), 1, 1, fill=False, edgecolor="black", lw=2)
                )

    plt.title(f"Line Loading Comparison  (Overload > {threshold}%)", fontsize=12)
    plt.xlabel("Line Index")
    plt.ylabel("")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":

    net = pp.create_empty_network()
    base_path = "Substation/data_Pandapower.xlsx"

    # Build Network
    create_buses(net, load_excel_data(base_path, "bus", strip_columns=True))
    create_loads(net, load_excel_data(base_path, "load"))
    create_sgen(net, load_excel_data(base_path, "sgen"))
    create_ext_grid(net, load_excel_data(base_path, "ext_grid"))
    create_lines(net, load_excel_data(base_path, "line", strip_columns=True))
    create_trafo(net, load_excel_data(base_path, "trafo"))

    # Run PPF (Before Battery)
    run_power_flow(net, result_file="results/Result.xlsx")

    # Detect Overloads
    overload_rows = get_overload_rows("results/Result.xlsx", threshold=70)

    # Battery Dispatch
    battery_discharge(net, overload_rows, base_path, discharge_mw=70)

    # Run PPF Again (After Battery)
    run_power_flow(net, result_file="results/Result2.xlsx")

    # write overload_line if exist after battery
    get_overload_rows2("results/Result2.xlsx", threshold=70)

    # Full Heatmap
    plot_loading_percent_heatmap(
        "results/Result.xlsx",
        "results/Result2.xlsx",
        label1="Scenario A - Before Battery Installation",
        label2="Scenario B - After Battery Installation",
        threshold=70,
    )
    # Overloaded Lines Only Heatmap
    plot_Overload_lines_heatmap(
        "results/Result.xlsx",
        "results/Result2.xlsx",
        overload_rows,
        label1="Scenario A - Before Battery",
        label2="Scenario B - After Battery",
        threshold=70,
    )
