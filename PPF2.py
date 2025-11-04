import pandapower as pp
import pandas as pd
import os
import matplotlib.pyplot as plt
import seaborn as sns


def clean_numeric_columns(df):
    for col in df.columns:
        if df[col].dtype == object:
            # Remove spaces and replace comma decimals
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.replace(",", ".")
            )
            # Try converting to numeric
            try:
                df[col] = pd.to_numeric(df[col])
            except Exception:
                # leave as string if cannot convert
                pass
    return df

def load_excel_data(file_path, sheet_name, index_col=0, strip_columns=False):
    df = pd.read_excel(file_path, sheet_name=sheet_name, index_col=index_col)
    if strip_columns:
        df.columns = df.columns.str.strip()
    df = clean_numeric_columns(df)  # clean the numbers
    return df


def build_network(base_path):
    net = pp.create_empty_network()
    
    # buses
    df_bus = load_excel_data(base_path, "bus", strip_columns=True)
    for _, row in df_bus.iterrows():
        pp.create_bus(net, vn_kv=row["vn_kv"], name=row["name"])

    # external grid
    df_ext_grid = load_excel_data(base_path, "ext_grid")
    for i in df_ext_grid.index:
        pp.create_ext_grid(net, **df_ext_grid.loc[i].to_dict())

    # lines
    df_lines = load_excel_data(base_path, "line", strip_columns=True)
    df_lines["length_km"] = (
        df_lines["length_km"].astype(str).str.replace(",", ".").astype(float)
    )
    for _, row in df_lines.iterrows():
        pp.create_line_from_parameters(
            net,
            from_bus=int(row["from_bus"]),
            to_bus=int(row["to_bus"]),
            length_km=row["length_km"],
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

    # transformers
    df_trafo = load_excel_data(base_path, "trafo")
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

    return net
# detect time stamp column 
def detect_timestamp_col(df):
    
    # return index (int) of timestamp column if detected, else None
    for i, c in enumerate(df.columns):
        if "time" in c.lower() or "timestamp" in c.lower() or "hour" in c.lower():
            return i
    c0 = df.columns[0]
    try:
        s = pd.to_numeric(df[c0], errors="coerce")
        if s.notna().all() and s.iloc[0] == 1 and s.iloc[-1] == len(df):
            return 0
    except Exception:
        pass
    return None

def build_name_to_col_map(net, df_ts, element, csv_columns):
    
    mapping = {}
    #convert lowered columns for matching
    cols_lower = {c: c.lower().strip() for c in csv_columns}
    for idx, row in element.iterrows():
        name = str(row.get("name", "")).strip()
        bus = str(row.get("bus", "")).strip()
        found = None
        if name:
            name_low = name.lower().strip()
            # exact match
            for c, cl in cols_lower.items():
                if cl == name_low:
                    found = c; break
            # case sensitve partial match
            if not found:
                for c, cl in cols_lower.items():
                    if name_low in cl or cl in name_low:
                        found = c; break
    # try matching by bus number string if name not matched
    if not found and bus and bus.isdigit():
        for c, cl in cols_lower.items():
            if bus == cl or bus in cl:
                found = c; break 
    # fallback: if only one column available
    if not found:
        if len(csv_columns) == 1:
            found = csv_columns[0]
        else:
            found = csv_columns[0]
            print(f"Warning: Could not find matching TS column for element '{name}' (idx {idx}). Falling back to '{found}'.")
        mapping[idx] = found
    return mapping
        


# load time series data
def Load_timeseriesdata(net, base_path, sgen_csv= None, load_csv=None, sgen_bus=0):
    df_load = load_excel_data(base_path, "load")
    #df_sgen = load_excel_data(base_path, "sgen")
  
    load_list = []
    sgen_list = []
    sgen_map = {}
    
    #create Loads from excel
    for _, row in df_load.iterrows():
        load = pp.create_load(net, bus=int(row["bus"]), p_mw= 0.0, q_mvar=0.0, name=row["name"])
        load_list.append(load)
   

        
    # load CSVs
    if load_csv is not None:
        df_load_ts = pd.read_csv(load_csv)
    else:
        df_load_ts = pd.DataFrame()
        
    if sgen_csv is not None:
        df_sgen_ts = pd.read_csv(sgen_csv)
    else:
        df_sgen_ts = pd.DataFrame()
        
    # detect and drop timestamp columns
    def clean_ts_df(df):
        if df is None or df.empty:
            return df, None
        ts_idx = detect_timestamp_col(df)
        
        if ts_idx is not None:
            ts_col = df.columns[ts_idx]
            df_no_ts = df.drop(columns=[ts_col])
            return df_no_ts, ts_col
        return df.copy(), None
    
    df_load_ts, Load_ts_timestamp_col = clean_ts_df(df_load_ts)
    df_sgen_ts, sgen_ts_timestamp_col = clean_ts_df(df_sgen_ts)
    
# if dataframe is empty leave empty
    load_cols = df_load_ts.columns.tolist() if (df_load_ts is not None and not df_load_ts.empty) else[]
    sgen_cols = df_sgen_ts.columns.tolist() if (df_sgen_ts is not None and not df_sgen_ts.empty) else[]

# Assign each sgen site to a bus (default: all to sgen_bus) 
    if isinstance(sgen_bus, int): 
        bus_list = [sgen_bus] * len(sgen_cols)
    else:
        bus_list = sgen_bus 
    
    for i, col in enumerate(sgen_cols): 
        bus = bus_list[i] 
        sgen = pp.create_sgen(net, bus=bus, p_mw=0.0, q_mvar=0.0, name=col) 
        sgen_list.append(sgen) 
        sgen_map[sgen] = col


# map net elements to csv columns
    load_map = build_name_to_col_map(net, df_load_ts, net.load, load_cols) if load_cols else {}
    #sgen_map = build_name_to_col_map(net, df_sgen_ts, net.sgen, sgen_cols) if sgen_cols else {}
    
    return load_list, sgen_list, df_load_ts, df_sgen_ts, sgen_map, load_map
    


def run_powerflow(net, load_data, sgen_data, load_list, sgen_list, load_map, sgen_map, result_file="results"):
    if not os.path.exists(result_file):
        os.makedirs(result_file)

    # determine timesteps from the time-series df (prefer load df if present)
    if load_data is not None and not load_data.empty:
        timesteps = range(len(load_data))
    elif sgen_data is not None and not sgen_data.empty:
        timesteps = range(len(sgen_data))
    else:
        raise ValueError("No time series data provided for loads or PV.")

    
    # power flow results
    bus_results_all = []
    line_loading_results_all = []
    line_p_results_all = []
    
    


    for t in timesteps:
        #assign load and PV generation
        for i in load_list:
            if i in load_map and load_map[i] in load_data.columns:
                val = pd.to_numeric(load_data.iloc[t][load_map[i]], errors = "coerce")
                if pd.isna(val):
                    val = 0.0
                net.load.at[i, "p_mw"] = float(val)
            else:
                net.load.at[i, "p_mw"] = 0.0
                
        
        
        # assign sgen (PV/wind) values per mapping    
        for i in sgen_list:
            if i in sgen_map and sgen_map[i] in sgen_data.columns:
                val = pd.to_numeric(sgen_data.iloc[t][sgen_map[i]], errors="coerce")
                if pd.isna(val):
                    val = 0.0
                net.sgen.at[1, "p_mw"] = float(val)
            else:
                net.sgen.at[i, "p_mw"] = 0.0
                    
                    
        # pp.runpp(net)
        try:
            pp.runpp(net)
        except pp.LoadflowNotConverged:
            print(f"Power flow did not converge at timestep{t}")
            print(" Total Load (MW):", net.load["p_mw"].sum())
            print(" Total PV (MW):", net.sgen["p_mw"].sum())
            print(" Slack bus:", net.ext_grid.bus.values)
            continue
        
       
        bus_res = pd.Series(net.res_bus["vm_pu"].values, index=net.res_bus.index, name=t)
        line_loading_res = pd.Series(net.res_line["loading_percent"].values, index=net.res_line.index, name=t)
        line_p_to_res = pd.Series(net.res_line["p_to_mw"].values, index=net.res_line.index, name=t)
        
        
        # Add timestep info
        bus_res["timestep"] = t
        line_loading_res["timestep"] = t
        
        
        bus_results_all.append(bus_res)
        line_loading_results_all.append(line_loading_res)
        line_p_results_all.append(line_p_to_res)

        
                        
#   Convert result lists to DataFrames
    bus_res_df = pd.DataFrame(bus_results_all)
    bus_res_df.columns = [f"Bus_{str(c)}_vm_pu" for c in bus_res_df.columns]

    line_loading_res_df = pd.DataFrame(line_loading_results_all)
    line_loading_res_df.columns = [f"Line_{str(c)}_loading%" for c in line_loading_res_df.columns]

    line_p_res_df = pd.DataFrame(line_p_results_all)
    line_p_res_df.columns = [f"Line_{str(c)}_p_to_MW" for c in line_p_res_df.columns]
    
    
    def drop_time_columns(df):
        drop_cols = [c for c in df.columns if "time" in c.lower() or "date" in c.lower()]
        return df.drop(columns=drop_cols, errors="ignore")

    bus_res_df = drop_time_columns(bus_res_df)
    line_loading_res_df = drop_time_columns(line_loading_res_df)
    line_p_res_df = drop_time_columns(line_p_res_df)

    # dentify useful columns
    bus_cols = [c for c in bus_res_df.columns if "vm_pu" in c]
    line_load_cols = [c for c in line_loading_res_df.columns if "loading%" in c]
    line_p_mw_cols = [c for c in line_p_res_df.columns if "p_to_MW" in c]
    

    # Prepare summary results
    summary_results = []

    for t in range(len(bus_res_df)):
        vm_values = bus_res_df.loc[t, bus_cols]

        if vm_values.dropna().empty:
            max_vm = min_vm = None
            max_vm_bus = min_vm_bus = "None"
        else:
            max_vm = vm_values.max()
            min_vm = vm_values.min()
            max_vm_bus = vm_values.idxmax()
            min_vm_bus = vm_values.idxmin()

        load_values = line_loading_res_df.loc[t, line_load_cols]
        if load_values.dropna().empty:
            max_load = min_load = None
            max_load_line = min_load_line = "None"
        else:
            max_load = load_values.max()
            min_load = load_values.min()
            max_load_line = load_values.idxmax()
            min_load_line = load_values.idxmin()

        p_mw_values = line_p_res_df.loc[t, line_p_mw_cols]
        if p_mw_values.dropna().empty:
            max_p_mw = min_p_mw = None
            max_p_mw_line = min_p_mw_line = "None"
        else:
            max_p_mw = p_mw_values.max()
            min_p_mw = p_mw_values.min()
            max_p_mw_line = p_mw_values.idxmax()
            min_p_mw_line = p_mw_values.idxmin()

        mean_loading_res = line_loading_res_df.loc[t, line_load_cols].mean()

        summary_results.append({
            "timestep": t,
            "max_loading_percent": max_load,
            "max_loading_line": max_load_line,
            "min_loading_percent": min_load,
            "min_loading_line": min_load_line,
            "mean_loading_percent": mean_loading_res,
            "max_vm_pu": max_vm,
            "max_vm_bus": max_vm_bus,
            "min_vm_pu": min_vm,
            "min_vm_bus": min_vm_bus,
            "max_p_mw": max_p_mw,
            "max_p_mw_line": max_p_mw_line,
            "min_p_mw": min_p_mw,
            "min_p_mw_line": min_p_mw_line
        })

    # --- Combine line results ---
    line_results_all = pd.concat([line_loading_res_df, line_p_res_df], axis=1)

    # --- Save results ---
    df_results = pd.DataFrame(summary_results)
    df_results.to_csv(os.path.join(result_file, "PPF2results.csv"), index=False)
    bus_res_df.to_csv(os.path.join(result_file, "bus_result.csv"), index=False)
    line_results_all.to_csv(os.path.join(result_file, "line_results.csv"), index=False)

    print(f"Conventional power flow completed for {len(timesteps)} timesteps.")
    print(f"Results saved to: {os.path.join(result_file, 'PPF2results.csv')}")

    return df_results, bus_res_df, line_results_all

    
def plot_histogram(filepath):
    # Load your CSV file 
    df_plot = pd.read_csv(filepath, index_col=False)
    # get the mean of the loading%
    loading_col = [c for c in df_plot.columns if "loading%" in c]
    df_plot["mean_loading_percent"] = df_plot[loading_col].mean(axis=1)
    
    
    # Plot mean loading percent vs timestep
    plt.figure(figsize=(10, 6))
    plt.plot(df_plot.index, df_plot["mean_loading_percent"], marker='o', linestyle='-', color='b', label='Loading %')
    # plt.hist(df_plot["loading_percent"], bins=15, color='skyblue', edgecolor='black', alpha=0.8)
    
    plt.title("Line Loading Percentage vs Timesteps", fontsize=12)
    plt.xlabel("Timesteps", fontsize=12)
    plt.ylabel("Loading (%)", fontsize=12)
    plt.legend(loc="upper right", bbox_to_anchor=(1.2, 1))
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    
    # --- Save and show ---
    plt.savefig("line_loading_vs_timestep.png", dpi=300)
    plt.show()
    
    
# Heat Map of loading%
def heat_map(filepath):
    # --- Load your CSV file ---
    df_plot = pd.read_csv(filepath, index_col=False)
    
    #get the loading_col
    loading_col = [c for c in df_plot.columns if "loading%" in c]
    heatmap_data = df_plot[loading_col].transpose()
    plt.figure(figsize=(14, 8))
    sns.heatmap( 
                heatmap_data,
                cmap="viridis", 
                cbar_kws = {"label": "Loading(%)"},
                xticklabels=200 if len(df_plot) > 200 else 1,
                vmin=0, vmax=100)
    
    plt.title("Heatmap of Loading(%) Accross Timesteps", fontsize = 14)
    plt.xlabel("Timestep")
    plt.ylabel("Line")
    plt.tight_layout()
    
    plt.savefig("line_loading_heatmap.png", dpi=300)
    plt.show()


def detect_overload(file_path, treshold=70):
    pass

def congestion_management(file_path):
    pass


if __name__ == "__main__":
    # File paths
    base_path = "Substation/data_Pandapower.xlsx"
    pv_file = "timeseriesdata/wind_data.csv"
    load_file = "timeseriesdata/electrodeHeater.csv"

    # Load input data
    pv_data = pd.read_csv(pv_file)      # assumed column: p_mw
    load_data = pd.read_csv(load_file)  # assumed column: p_mw

    # Build static network
    net = build_network(base_path)

    # # Attach PV and Load time series
    # load_list, sgen_list = Load_timeseriesdata(net, base_path)
    
    
    # load_list, sgen_list, load_ts_df, sgen_ts_df, load_map, sgen_map = \
    #     Load_timeseriesdata(net, base_path, sgen_csv=pv_file, load_csv=load_file)
    


    # # Run time-series power flow
    # run_powerflow(net, load_data, pv_data, load_list, sgen_list, load_map, sgen_map, result_file="results")
    
    # # Plot histogram
    # plot_histogram("results/line_results.csv")
    
    #plot heatmap
    heat_map("results/line_results.csv")
    
    