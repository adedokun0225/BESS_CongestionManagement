import os
import csv
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np


# histogram
def plot_timeseries(filepath):
    # Load your CSV file
    df_plot = pd.read_csv(filepath, index_col=False)
    # get the mean of the loading%
    loading_col = [c for c in df_plot.columns if "loading%" in c]
    df_plot["max_loading_percent"] = df_plot[loading_col].max(axis=1)

    # Plot mean loading percent vs timestep
    plt.figure(figsize=(10, 6))
    plt.plot(
        df_plot.index,
        df_plot["max_loading_percent"],
        marker="o",
        linestyle="-",
        color="b",
        label="Loading %",
    )
    # plt.hist(df_plot["loading_percent"], bins=15, color='skyblue', edgecolor='black', alpha=0.8)

    plt.title("Temporal Variation of Maximum Network Line Loading", fontsize=12)
    plt.xlabel("Timesteps", fontsize=12)
    plt.ylabel("Loading (%)", fontsize=12)
    plt.legend(loc="upper right", bbox_to_anchor=(1.2, 1))
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()

    # Save and show
    plt.savefig("line_loading_vs_timestep.png", dpi=300)
    plt.show()


# Heat Map of loading%
def heat_map(filepath):
    # --- Load your CSV file ---
    df_plot = pd.read_csv(filepath, index_col=False)

    # get the loading_col
    loading_col = [c for c in df_plot.columns if "loading%" in c]
    heatmap_data = df_plot[loading_col].transpose()
    plt.figure(figsize=(14, 8))
    sns.heatmap(
        heatmap_data,
        cmap="viridis",
        cbar_kws={"label": "Loading(%)"},
        xticklabels=200 if len(df_plot) > 200 else 1,
        vmin=0,
        vmax=100,
    )

    plt.title("Heatmap of Loading(%) Accross Timesteps", fontsize=14)
    plt.xlabel("Timestep")
    plt.ylabel("Line")
    plt.tight_layout()
    plt.savefig("line_loading_heatmap.png", dpi=300)
    plt.show()


def plot_line_loading_histogram(file_path, bins=50):

    df = pd.read_csv(file_path)
    loading_cols = [col for col in df.columns if "loading%" in col]
    loading_values = df[loading_cols].values.flatten()
    # remove NAN values
    loading_values = loading_values[~np.isnan(loading_values)]

    # plot histogram
    plt.figure(figsize=(10, 6))
    plt.hist(loading_values, bins=bins)

    plt.yscale("log")
    plt.xlabel("line loading (%)")
    plt.ylabel("frequency (log scale)")
    plt.title("Distribution of Transmission Line Loading After congestion")
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def plot_top_congested_lines(file_path, top=10):

    df = pd.read_csv(file_path)
    loading_cols = [col for col in df.columns if "loading%" in col]
    max_loading = df[loading_cols].max()
    top_lines = max_loading.sort_values(ascending=False).head(top)

    plt.figure(figsize=(10, 6))
    plt.bar(top_lines.index, top_lines.values)

    plt.xticks(rotation=60)
    plt.ylabel("Maximum Line Loading (%)")
    plt.xlabel("Transmission Lines")
    plt.title(f"top {top} Most Congested Transmission Lines")
    plt.grid(True)

    plt.tight_layout()
    plt.show()


def plot_congestion_duration_curve(file_path):

    df = pd.read_csv(file_path)
    loading_cols = [col for col in df.columns if "loading%" in col]
    loading_values = df[loading_cols].values.flatten()
    # remove NAN values
    loading_values = loading_values[~np.isnan(loading_values)]
    # sort loading values in descending order
    sorted_loading = np.sort(loading_values)[::-1]
    # create hour index
    hours = np.arange(len(sorted_loading))

    # plot congestion duration curve
    plt.figure(figsize=(10, 6))
    plt.plot(hours, sorted_loading)
    # Thermal limit reference line
    plt.axhline(y=80, linestyle="--")

    plt.xlabel("Hours")
    plt.ylabel("Line Loading (%)")
    plt.title("congestion Duration Curve of Transmission Lines")
    plt.grid(True)

    plt.tight_layout()
    plt.show()


# Before and After Bess
def plot_max_line_loading(file_path_before, file_path_after, threshold=80):

    df_after = pd.read_csv(file_path_after)
    loading_cols_after = [col for col in df_after.columns if "loading%" in col]
    df_after["max_loading"] = df_after[loading_cols_after].max(axis=1)

    plt.figure(figsize=(12, 6))
    plt.plot(
        df_after["timestep"], df_after["max_loading"], label="After BESS", linewidth=1.5
    )

    # Before Bess
    if file_path_before is not None:
        df_before = pd.read_csv(file_path_before)

        loading_cols_before = [col for col in df_before.columns if "loading%" in col]
        df_before["max_loading"] = df_before[loading_cols_before].max(axis=1)

        plt.plot(
            df_before["timestep"],
            df_before["max_loading"],
            label="Before BESS",
            linewidth=0.7,
        )

    # labels
    plt.xlabel("Time (hours)")
    plt.ylabel("Maximum Line Loading(%)")
    plt.title("Maximum Line Loading per Timestep")

    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def plot_bess_dispatch_and_soc(file_path, save_path=None):
    df = pd.read_csv(file_path)
    dispatch_per_timestep = df.groupby("timestep")["p_dispatch_mw"].sum()
    soc_avg_per_timestep = df.groupby("timestep")["soc_after"].mean()

    timesteps = dispatch_per_timestep.index

    plt.figure(figsize=(12, 5))
    plt.plot(timesteps, dispatch_per_timestep, linewidth=1.5)

    plt.xlabel("Time (hours)")
    plt.ylabel("BESS Power Dispatch (MW)")
    plt.title("Battery Dispatch Profile")
    plt.grid(True)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path + "_dispatch.png", dpi=300)

    plt.show()

    # SOC profile
    plt.figure(figsize=(12, 5))
    plt.plot(timesteps, soc_avg_per_timestep, linewidth=1.5)

    plt.xlabel("Time (hours)")
    plt.ylabel("State of Charge (SOC)")
    plt.title("Battery State of Charge Over Time")
    plt.grid(True)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path + "_soc.png", dpi=300)

    plt.show()


def plot_line_loading_timeseries(
    file_before,
    file_after,
    lines_to_plot=None,
    threshold=80,
    save_path=None,
):
    df_before = pd.read_csv(file_before)
    df_after = pd.read_csv(file_after)

    loading_cols_before = [col for col in df_before.columns if "loading%" in col]
    loading_cols_after = [col for col in df_after.columns if "loading%" in col]

    if lines_to_plot is None:
        max_vals = df_before[loading_cols_before].max().sort_values(ascending=False)
        top_cols = max_vals.head(3).index
        lines_to_plot = [int(col.split("_")[1]) for col in top_cols]

    plt.figure(figsize=(12, 6))
    for line in lines_to_plot:
        col_name = f"lines_{line}_loading%"

        if col_name in df_before.columns and col_name in df_after.columns:
            plt.plot(
                df_before["timestep"],
                df_before[col_name],
                linestyle="--",
                label=f"Line {line} (Before)",
            )
            plt.plot(
                df_after["timestep"], df_after[col_name], label=f"Line {line} (After)"
            )
    # Threshold line
    plt.axhline(y=threshold, linestyle=":", label=f"Threshold ({threshold}%)")

    # Labels and formatting
    plt.xlabel("Time (hours)")
    plt.ylabel("Line Loading (%)")
    plt.title("Line Loading Time-Series (Before vs After BESS)")

    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    # Save if needed
    if save_path:
        plt.savefig(save_path, dpi=300)

    plt.show()


# congestion duration
def plot_congestion_duration_curve(
    file_before, file_after, threshold=80, save_path=None
):

    # === Load data ===
    df_before = pd.read_csv(file_before)
    df_after = pd.read_csv(file_after)

    # === Extract loading columns ===
    loading_cols_before = [col for col in df_before.columns if "loading%" in col]
    loading_cols_after = [col for col in df_after.columns if "loading%" in col]

    # === Compute max loading per timestep ===
    max_before = df_before[loading_cols_before].max(axis=1)
    max_after = df_after[loading_cols_after].max(axis=1)

    # === Sort in descending order (duration curve) ===
    sorted_before = max_before.sort_values(ascending=False).reset_index(drop=True)
    sorted_after = max_after.sort_values(ascending=False).reset_index(drop=True)

    hours = range(len(sorted_before))

    # === Plot ===
    plt.figure(figsize=(12, 6))

    plt.plot(hours, sorted_after, label="After BESS", linewidth=1.5)
    plt.plot(hours, sorted_before, label="Before BESS", linewidth=1.5)

    # Threshold line
    plt.axhline(y=threshold, linestyle="--", label=f"Threshold ({threshold}%)")

    # Labels
    plt.xlabel("Sorted Time (hours)")
    plt.ylabel("Maximum Line Loading (%)")
    plt.title("Congestion Duration Curve (Before vs After BESS)")

    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    # Save if needed
    if save_path:
        plt.savefig(save_path, dpi=300)

    plt.show()


if __name__ == "__main__":

    # # Plot histogram
    # plot_timeseries("results/res_100%/line_results_Bctrl.csv")
    # plot_timeseries("7 iterations/line_results_ctrl_fixed.csv")

    # #plot heatmap
    # heat_map("results/line_results.csv")

    # plot histogram
    # plot_line_loading_histogram("7 iterations/line_results_Bctrl.csv", bins=50)
    # plot_line_loading_histogram("7 iterations/line_results_ctrl_fixed.csv", bins=50)

    # # plot bar
    # plot_top_congested_lines("results/res_100%/line_results_Bctrl.csv")

    # # plot CDC
    # plot_congestion_duration_curve("results/line_results_Bctrl.csv")
    # plot_congestion_duration_curve("results/line_results_ctrl.csv")

    # # plot maxloading
    # plot_max_line_loading(
    #     file_path_before="7 iterations/line_results_Bctrl.csv",
    #     file_path_after="7 iterations/line_results_ctrl_fixed.csv",
    #     threshold=80,
    # )

    # # plot bess and soc
    # plot_bess_dispatch_and_soc("7 iterations/battery_dispatch_log.csv")

    # # plot line_loading timeseries
    # plot_line_loading_timeseries(
    #     "15 iterations/line_results_Bctrl.csv",
    #     "15 iterations/line_results_ctrl_fixed.csv",
    # )

    # # plot line_loading timeseries for before and after
    # plot_line_loading_timeseries(
    #     "line_results_Bctrl.csv",
    #     "line_results_ctrl.csv",
    #     lines_to_plot=[38, 105, 199],
    #     threshold=80,
    #     save_path="line_loading_timeseries.png",
    # )

    # plot congestion duration curve
    plot_congestion_duration_curve(
        "7 iterations/line_results_Bctrl.csv",
        "7 iterations/line_results_ctrl_fixed.csv",
        threshold=80,
        save_path="congestion_duration_curve.png",
    )
