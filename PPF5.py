import pandapower as pp
import pandas as pd
import os
import matplotlib.pyplot as plt
import seaborn as sns
import re
from BatteryModel2 import BatteryModel
import csv
import numpy as np
import logging
from pandapower.topology import calc_distance_to_bus
import difflib


def clean_numeric_columns(df):
    for col in df.columns:
        if df[col].dtype == object:
            # Remove spaces and replace comma decimals
            df[col] = df[col].astype(str).str.strip().str.replace(",", ".")
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


def normalize(s: str):
    if s is None:
        return ""
    s = str(s).lower()
    s = re.sub(r"[^a_z0-9]+", " ", s)
    tokens = s.split()
    return tokens


def token_similarity(a: str, b: str):
    # compute token overlap similarity
    ta = set(normalize(a))
    tb = set(normalize(b))
    if not ta or not tb:
        return 0
    return len(ta & tb) / len(ta | tb)


def build_name_to_col_map(names, available_cols, score_threshold=0.60):

    mapping = {}
    used_cols = set()
    # Pre-normalize column names for fast lookup
    normalized_cols = {c: normalize(c) for c in available_cols}

    for name in names:
        name_str = str(name)
        name_norm = normalize(name_str)

        best_col = None
        best_score = 0

        for col in available_cols:
            if col in used_cols:
                continue

            col_norm = normalized_cols[col]

            # Exact match
            if name_str == col:
                best_col = col
                best_score = 1.0
                break

            # Case-insensitive direct match
            if name_str.lower() == col.lower():
                best_col = col
                best_score = 0.95
                break

            # Token similarity match
            tok_sim = token_similarity(name_str, col)
            if tok_sim > best_score:
                best_score = tok_sim
                best_col = col

            # Fuzzy matching as last resort
            fuzz = difflib.SequenceMatcher(None, name_str.lower(), col.lower()).ratio()
            if fuzz > best_score:
                best_score = fuzz
                best_col = col

        # Only accept if strong enough match
        if best_score >= score_threshold:
            mapping[name] = best_col
            used_cols.add(best_col)
        else:
            mapping[name] = None

    return mapping


# load time series data
def Load_timeseriesdata(net, base_path, sgen_csv=None, load_csv=None, sgen_bus=0):
    df_load = load_excel_data(base_path, "load")
    # df_sgen = load_excel_data(base_path, "sgen")

    load_list = []
    sgen_list = []
    sgen_map = {}

    # create Loads from excel
    for _, row in df_load.iterrows():
        load = pp.create_load(
            net, bus=int(row["bus"]), p_mw=0.0, q_mvar=0.0, name=row["name"]
        )
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
    load_cols = (
        df_load_ts.columns.tolist()
        if (df_load_ts is not None and not df_load_ts.empty)
        else []
    )
    sgen_cols = (
        df_sgen_ts.columns.tolist()
        if (df_sgen_ts is not None and not df_sgen_ts.empty)
        else []
    )

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
    if load_cols:
        load_names = [
            str(row["name"]) if not pd.isna(row["name"]) else str(idx)
            for idx, row in net.load.iterrows()
        ]

    used_map = build_name_to_col_map(
        names=load_names, available_cols=load_cols, score_threshold=0.35
    )

    load_map = {}
    for idx, row in net.load.iterrows():
        name = str(row["name"])
        if name in used_map:
            load_map[idx] = used_map[name]
        # if load_cols
        # else {}

    return load_list, sgen_list, df_load_ts, df_sgen_ts, sgen_map, load_map


# First Test power flow
# def run_powerflow(
#     net,
#     load_data,
#     sgen_data,
#     load_list,
#     sgen_list,
#     load_map,
#     sgen_map,
#     result_file="results",
# ):
#     if not os.path.exists(result_file):
#         os.makedirs(result_file)

#     # determine timesteps from the time-series df (prefer load df if present)
#     if load_data is not None and not load_data.empty:
#         timesteps = range(len(load_data))
#     elif sgen_data is not None and not sgen_data.empty:
#         timesteps = range(len(sgen_data))
#     else:
#         raise ValueError("No time series data provided for loads or PV.")

#     # power flow results list
#     bus_results_all = []
#     line_loading_results_all = []
#     line_p_results_all = []

#     for t in timesteps:
#         # assign load and PV generation
#         for i in load_list:
#             if i in load_map and load_map[i] in load_data.columns:
#                 val = pd.to_numeric(load_data.iloc[t][load_map[i]], errors="coerce")
#                 if pd.isna(val):
#                     val = 0.0
#                 net.load.at[i, "p_mw"] = float(val)
#             else:
#                 net.load.at[i, "p_mw"] = 0.0

#         # assign sgen (PV/wind) values per mapping
#         for i in sgen_list:
#             if i in sgen_map and sgen_map[i] in sgen_data.columns:
#                 val = pd.to_numeric(sgen_data.iloc[t][sgen_map[i]], errors="coerce")
#                 if pd.isna(val):
#                     val = 0.0
#                 net.sgen.at[1, "p_mw"] = float(val)
#             else:
#                 net.sgen.at[i, "p_mw"] = 0.0

#         # pp.runpp(net)
#         try:
#             pp.runpp(net)
#         except pp.LoadflowNotConverged:
#             print(f"Power flow did not converge at timestep{t}")
#             print(" Total Load (MW):", net.load["p_mw"].sum())
#             print(" Total PV (MW):", net.sgen["p_mw"].sum())
#             print(" Slack bus:", net.ext_grid.bus.values)
#             continue

#         bus_res = pd.Series(
#             net.res_bus["vm_pu"].values, index=net.res_bus.index, name=t
#         )
#         line_loading_res = pd.Series(
#             net.res_line["loading_percent"].values, index=net.res_line.index, name=t
#         )
#         line_p_to_res = pd.Series(
#             net.res_line["p_to_mw"].values, index=net.res_line.index, name=t
#         )

#         # Add timestep info
#         bus_res["timestep"] = t
#         line_loading_res["timestep"] = t

#         # power flow results list
#         bus_results_all.append(bus_res)
#         line_loading_results_all.append(line_loading_res)
#         line_p_results_all.append(line_p_to_res)

#     #   Convert result lists to DataFrames
#     bus_res_df = pd.DataFrame(bus_results_all)
#     bus_res_df.columns = [f"Bus_{str(c)}_vm_pu" for c in bus_res_df.columns]

#     line_loading_res_df = pd.DataFrame(line_loading_results_all)
#     line_loading_res_df.columns = [
#         f"Line_{str(c)}_loading%" for c in line_loading_res_df.columns
#     ]

#     line_p_res_df = pd.DataFrame(line_p_results_all)
#     line_p_res_df.columns = [f"Line_{str(c)}_p_to_MW" for c in line_p_res_df.columns]

#     # Combine line results
#     line_results_all = pd.concat([line_loading_res_df, line_p_res_df], axis=1)

#     bus_res_df.to_csv(os.path.join(result_file, "bus_result.csv"), index=True)
#     line_results_all.to_csv(os.path.join(result_file, "line_results.csv"), index=True)

#     print(f"Conventional power flow completed for {len(timesteps)} timesteps.")
#     print(f"Results saved to: {os.path.join(result_file, 'PPF2results.csv')}")

#     return bus_res_df, line_results_all


#### Main Approach ####


### Iterative Local Line Relief Approach ####
#### TO PICK ALL OVERLOAD LINES ####


def detect_overloaded_lines(net, threshold=80):

    # overloaded = net.res_line[net.res_line.loading_percent > threshold]
    if "loading_percent" in net.res_line.columns:
        overloaded_lines = net.res_line.index[
            net.res_line["loading_percent"] > threshold
        ].tolist()
    else:
        overloaded_lines = []

    if "loading_percent" in net.res_trafo.columns:
        overloaded_trafos = net.res_trafo.index[
            net.res_trafo.loading_percent > threshold
        ].tolist()
    else:
        overloaded_trafos = []

    return overloaded_lines, overloaded_trafos


#### COMPUTE ELECTRICAL DISTANCE ONCE EVERY TIMESTEPS ###
def get_bus_dist(net, ref_bus):

    return calc_distance_to_bus(net, ref_bus)


#### TO DISPATCH THE BATTERY TO THE CONGESTED LINES #####
def dispatch_bess_local2(
    net,
    bess_pool,
    congested_lines,
    overload_threshold,
    timestep_hrs,
    relief_factor=2.0,
    step_mw=30,
    max_iters=7,
):
    total_dispatch = 0.0
    max_dist = 15  # buses

    for line in congested_lines:
        loading = net.res_line.at[line, "loading_percent"]
        if loading <= overload_threshold:
            continue

        from_bus = net.line.at[line, "from_bus"]
        to_bus = net.line.at[line, "to_bus"]

        # Electrical dist ranking
        dist_from = calc_distance_to_bus(net, from_bus)
        dist_to = calc_distance_to_bus(net, to_bus)

        # collect candidates BESS with priorities
        Bess_Cand = []

        for bus, bess in bess_pool.items():
            if bess.soc <= 0.1:
                continue

            dist_f = dist_from.get(bus, 999)
            dist_t = dist_to.get(bus, 999)

            max_dist = 15  # buses

            dist = min(dist_f, dist_t)

            if dist <= max_dist:

                priority = bess.soc / (dist + 1e-3)  # SOC-weighted distance

                Bess_Cand.append((priority, bus, bess))

        if not Bess_Cand:
            continue

        # Highest impact first
        Bess_Cand.sort(reverse=True)

        loading_bf = net.res_line.at[line, "loading_percent"]

        # Iterative feedbach dispatch
        for _ in range(max_iters):
            loading_bf = net.res_line.at[line, "loading_percent"]
            if loading_bf <= overload_threshold:
                break

            dispatch_record = []

            # heuristc method
            for _, bus, bess in Bess_Cand:
                p_flow = net.res_line.at[line, "p_from_mw"]
                overload_mw = max(
                    0, abs(p_flow) * (loading_bf / 100 - overload_threshold / 100)
                )

                p_req = relief_factor * overload_mw
                p_req = max(step_mw, p_req)

                if p_flow > 0:
                    # flow from from_bus to to_bus
                    if dist_f < dist_t:
                        p_req = -abs(p_req)
                    else:
                        p_req = abs(p_req)
                else:
                    # reverse flow
                    if dist_f < dist_t:
                        p_req = abs(p_req)
                    else:
                        p_req = -abs(p_req)
                # if bus == to_bus:
                #     p_req = -p_req

                global_max_before = net.res_line.loading_percent.max()

                p_act = bess.dispatch(
                    p_set_mw=p_req, q_support=0.0, timestep_hours=timestep_hrs
                )

                dispatch_record.append((bess, p_act))
                total_dispatch += p_act

                pp.runpp(
                    net,
                    algorithm="nr",
                    max_iterations=30,
                    tolerance_mva=1e-6,
                    init="auto",
                    enforce_q_limits=True,
                    calculate_voltage_angles=True,
                )

                loading_new = net.res_line.at[line, "loading_percent"]
                global_max_after = net.res_line.loading_percent.max()

                # feedback check
                if global_max_after < global_max_before:
                    loading_bf = loading_new
                    continue
                else:
                    # rollback Ineffective action
                    # for bess, p_act in dispatch_record:
                    for bess, p_rol in dispatch_record:
                        bess.dispatch(
                            p_set_mw=-p_rol, q_support=0.0, timestep_hours=timestep_hrs
                        )

                        total_dispatch -= p_rol

                    pp.runpp(
                        net,
                        algorithm="nr",
                        max_iterations=30,
                        tolerance_mva=1e-6,
                        init="auto",
                        enforce_q_limits=True,
                        calculate_voltage_angles=True,
                    )

            if abs(loading_new - loading_bf) < 0.01:
                break

    return total_dispatch


# MAIN RUN POWER FLOW
def run_powerflow(
    net,
    load_data,
    sgen_data,
    load_list,
    sgen_list,
    sgen_map,
    load_map,
    bess_pool,
    result_file="results",
    timestep_hrs=1.0,
    overload_threshold=80,
    ctrl_iters=8,
):

    bus_results = []
    line_results = []
    trafo_results = []

    bus_results_ctrl = []
    line_results_ctrl = []
    # trafo_results_ctrl= []

    if not os.path.exists(result_file):
        os.makedirs(result_file)

    logging.basicConfig(
        filename="battery_dispatch.log",
        filemode="a",
        level=logging.INFO,
        format="%(asctime)s, %(message)s",
    )
    logger = logging.getLogger(__name__)

    log_path = os.path.join(result_file, "battery_dispatch_log.csv")
    with open(log_path, "w", newline="") as f:
        csv.writer(f).writerow(
            [
                "timestep",
                "bus_id",
                "p_dispatch_mw",
                "soc_before",
                "soc_after",
                "energy_before_mwh",
                "energy_after_mwh",
                "energy_change_mwh",
                "total_dispatch_mw",
            ]
        )

    # determine timesteps from the time-series df (prefer load df if present)
    if load_data is not None and not load_data.empty:
        steps = len(load_data)
    elif sgen_data is not None and not sgen_data.empty:
        steps = len(sgen_data)
    else:
        raise ValueError("No time series data provided for loads or PV.")

    timesteps = range(steps)
    Scaled_load_factor = 2

    for bess in bess_pool.values():
        bess.energystep_t = bess.energy_current

    for t in timesteps:
        # rest bess power
        for bess in bess_pool.values():
            bess.p_prev = 0.0
            bess.soc_before = bess.soc
            bess.energy_before = bess.energy_current
            net.sgen.at[bess.bess_index, "p_mw"] = 0.0

        # assign load and PV generation
        for i in load_list:
            if i in load_map and load_map[i] in load_data.columns:
                val = pd.to_numeric(load_data.iloc[t][load_map[i]], errors="coerce")
                if pd.isna(val):
                    val = 0.0
                net.load.at[i, "p_mw"] = float(val) / Scaled_load_factor
            else:
                net.load.at[i, "p_mw"] = 0.0

        # assign sgen (PV/wind) values per mapping
        bess_indices = {bess.bess_index for bess in bess_pool.values()}
        for i in sgen_list:
            if i in bess_indices:
                continue
            if i in sgen_map and sgen_map[i] in sgen_data.columns:
                val = pd.to_numeric(sgen_data.iloc[t][sgen_map[i]], errors="coerce")
                if pd.isna(val):
                    val = 0.0
                net.sgen.at[i, "p_mw"] = float(val) / Scaled_load_factor
            else:
                net.sgen.at[i, "p_mw"] = 0.0

        converged = True

        try:
            pp.runpp(net)
            # print(net.res_trafo[["loading_percent", "p_hv_mw", "p_lv_mw"]])
            # baseline_loading = get_line_loading(net)
            # baseline_max = baseline_loading.max()
            # print("Mapped columns:", len(mapped_columns))
            # print("Matched columns:", len(mapped_columns & available_columns))
            # print("Unmatched columns:", len(mapped_columns - available_columns))
            # print("Total Load (MW):", net.load["p_mw"].sum())
            # print("Mapped Gen (MW):", net.sgen["p_mw"].sum())
            # print("Time series total (row sum):", sgen_data.iloc[t].sum())
        except pp.LoadflowNotConverged:
            print(f"Power flow did not converge at timestep{t}")
            print("Total Load (MW):", net.load["p_mw"].sum())
            print("Mapped Gen (MW):", net.sgen["p_mw"].sum())
            print("Time series total (row sum):", sgen_data.iloc[t].sum())
            print("Slack bus:", net.ext_grid.bus.values)
            print("Power flow failed. Running diagnostic...")
            # run diagnostic
            pp.diagnostic(net, detailed=True)
            converged = False

        bus_row_Bctrl = {"timestep": t}
        for b in net.res_bus.index:
            bus_row_Bctrl[f"Bus_{b}_vm_pu"] = net.res_bus.at[b, "vm_pu"]
        bus_results.append(bus_row_Bctrl)

        line_row_Bctrl = {"timestep": t}
        for i in net.res_line.index:
            line_row_Bctrl[f"Line_{i}_loading%"] = net.res_line.at[i, "loading_percent"]
            line_row_Bctrl[f"Line_{i}_p_to_mw"] = net.res_line.at[i, "p_to_mw"]
        line_results.append(line_row_Bctrl)

        trafo_row_Bctrl = {"timestep": t}
        for i in net.res_trafo.index:
            trafo_row_Bctrl[f"Line_{i}_loading%"] = net.res_trafo.at[
                i, "loading_percent"
            ]
        trafo_results.append(trafo_row_Bctrl)

        #  Iterative Congestion Management

        if not converged:
            logger.warning(f"t={t}: PF failed, skipping timestep")
            continue
        else:
            p_prev = 0.0

        if converged and net.res_line.loading_percent.max() >= overload_threshold:

            for k in range(ctrl_iters):

                congested_lines, overloaded_trafos = detect_overloaded_lines(
                    net, overload_threshold
                )
                if len(congested_lines) == 0:
                    break

                congested_lines = sorted(
                    congested_lines,
                    key=lambda l: net.res_line.loading_percent[l],
                    reverse=True,
                )

                # compute Mw relief
                p_act = dispatch_bess_local2(
                    net=net,
                    bess_pool=bess_pool,
                    congested_lines=congested_lines,
                    overload_threshold=overload_threshold,
                    timestep_hrs=timestep_hrs,
                )

                # if abs(p_act - p_prev) < 0.05 * max(abs(p_prev), 1.0):
                # if abs(p_act - p_prev) < 0.01:
                if abs(p_act) < 0.01:
                    break  # no effective dispatch
                # # p_prev = p_act
                # run powerflow after dispatch
                pp.runpp(net, init="auto")
                # re-check congestion AFTER dispatch
                congested_lines, overloaded_trafos = detect_overloaded_lines(
                    net, overload_threshold
                )

                if len(congested_lines) == 0:
                    break
                try:
                    pp.runpp(net)
                    print(f"[t={t}] PF recovered after BESS dispatch")
                except pp.LoadflowNotConverged:
                    print(f"[t={t}] Controlled PF did not converge")
                    logger.warning(
                        f"[t={t}] Controlled PF diverged — stopping congestion control"
                    )
                    break
                print(f"[t={t}, iter={k}]")
                print(
                    "Total BESS MW:",
                    sum(net.sgen.at[b.bess_index, "p_mw"] for b in bess_pool.values()),
                )
                print(
                    f"[t={t}, iter={k}] max line loading:",
                    net.res_line.loading_percent.max(),
                )
                if (
                    net.res_line.loading_percent <= overload_threshold + 0.05
                ).all() and (
                    net.res_trafo.loading_percent <= overload_threshold + 0.05
                ).all():
                    break

        bus_row_ctrl = {"timestep": t}
        for b in net.res_bus.index:
            bus_row_ctrl[f"Bus_{b}_vm_pu"] = net.res_bus.at[b, "vm_pu"]
        bus_results_ctrl.append(bus_row_ctrl)

        line_row_ctrl = {"timestep": t}
        for i in net.res_line.index:
            line_row_ctrl[f"Line_{i}_loading%"] = net.res_line.at[i, "loading_percent"]
            line_row_ctrl[f"Line_{i}_p_to_mw"] = net.res_line.at[i, "p_to_mw"]
        line_results_ctrl.append(line_row_ctrl)

        # trafo_row_ctrl = {"timestep": t}
        # for i in net.res_trafo.index:
        #     trafo_row_ctrl[f"Line_{i}_loading%"] = net.res_trafo.at[
        #         i, "loading_percent"]
        #     trafo_row_ctrl[f"Line_{i}_p_to_mw"] = net.res_trafo.at[i, "p_to_mw"]
        # trafo_results_ctrl.append(trafo_row_ctrl)

        with open(log_path, "a", newline="") as f:
            writer = csv.writer(f)
            total_dispatch = 0.0
            for bus, bess in bess_pool.items():
                soc_after = bess.soc
                energy_after = bess.energy_current
                energy_change = energy_after - bess.energy_before
                total_dispatch += bess.p_prev

                writer.writerow(
                    [
                        t,
                        bus,
                        bess.p_prev,
                        bess.soc_before,
                        soc_after,
                        bess.energy_before,
                        energy_after,
                        energy_change,
                        total_dispatch,
                    ]
                )

    # ____save results___
    # before Control
    bus_results_df = pd.DataFrame(bus_results)
    line_results_df = pd.DataFrame(line_results)
    trafo_results_df = pd.DataFrame(trafo_results)

    bus_results_df.to_csv(os.path.join(result_file, "bus_results_Bctrl.csv"))
    line_results_df.to_csv(os.path.join(result_file, "line_results_Bctrl.csv"))
    trafo_results_df.to_csv(os.path.join(result_file, "trafo_results_Bctrl.csv"))

    # After control
    bus_df = pd.DataFrame(bus_results_ctrl)
    line_df = pd.DataFrame(line_results_ctrl)
    # trafo_df = pd.DataFrame(line_results_ctrl)

    bus_df.to_csv(os.path.join(result_file, "bus_results_ctrl.csv"))
    line_df.to_csv(os.path.join(result_file, "line_results_ctrl.csv"))
    # trafo_df.to_csv(os.path.join(result_file, "trafo_results_Bctrl.csv"))

    print(f"[PPF2] Completed {steps} timesteps. Logs at {result_file}")


#### TEST BESS DISPATCH ###
def dispatch_bess_local(
    net,
    bess_pool,
    congested_lines,
    overload_threshold,
    timestep_hrs,
    relief_factor=4,
    max_iter_per_line=4,
):
    total_dispatch = 0.0

    for line in congested_lines:
        loading = net.res_line.at[line, "loading_percent"]
        if loading <= overload_threshold:
            continue

        from_bus = net.line.at[line, "from_bus"]
        to_bus = net.line.at[line, "to_bus"]

        # Relief estimate
        pflow = abs(net.res_line.at[line, "p_from_mw"])
        overload_mw = (loading - overload_threshold) / 100 * pflow
        if overload_mw <= 0:
            continue

        # Dispatch BESS at adjacent buses
        for bus in [from_bus, to_bus]:
            if bus not in bess_pool:
                continue

            bess = bess_pool[bus]

            # Heuristic: discharge on from_bus, charge on to_bus
            p_req = relief_factor * overload_mw

            if bus == to_bus:
                p_req = -p_req

            for _ in range(max_iter_per_line):
                p_act = bess.dispatch(
                    p_set_mw=p_req, q_support=0.0, timestep_hours=timestep_hrs
                )
                total_dispatch += p_act

                pp.runpp(net)
                loading_new = net.res_line.at[line, "loading_percent"]

                # stop if no improvement
                if loading_new >= loading - 0.02:
                    bess.dispatch(-p_act, 0.0, timestep_hrs)
                    pp.runpp(net)
                    continue

                loading = loading_new

    return total_dispatch

    p_act *= 0.6


### OTHER TEST METHODS ###########


### Second Approach ###
#### Required Relief Estimation and Battery Energy Storage Dispatch #####
def compute_required_relief(net, overloaded, threshold=80):
    relief = {}

    for idx in overloaded:
        loading = net.res_line.at[idx, "loading_percent"]
        p_from = abs(net.res_line.at[idx, "p_from_mw"])
        p_to = abs(net.res_line.at[idx, "p_to_mw"])
        p_flow = max(p_from, p_to)

        # fraction of overload
        # overload_frac = max(0.0, (loading - threshold) / threshold)

        # #sensitivity correction ptdf mag
        # sensitivity = 0.3
        # damping = 0.5
        # # MW reduction neeed
        # required_mw = damping * (overload_frac * p_flow / sensitivity)

        # required_mw = min(required_mw, 0.6 * p_flow)

        # relief[idx] = required_mw

        # fraction of overload
        overload_frac = (loading - threshold) / 80

        # MW reduction neeed
        required_mw = overload_frac * p_flow

        required_mw = min(required_mw, 1.0 * p_flow)

        relief[idx] = required_mw

    return relief


# def compute_required_relief(
#     net,
#     bess_bus,
#     bess_pool,
#     ptdf=None,
#     threshold=80,
#     safety_margin=0.98
#     ):

#     overloaded_lines = net.res_line.loading_percent > threshold

#     if not overloaded_lines.any():
#         return 0.0, {"congested": False}

#     p_actual_total = 0.0
#     detail = []

#     for line_idx in net.line.index[overloaded_lines]:
#         loading = net.res_line.at[line_idx, "loading_percent"]
#         threshold = threshold

#     # Approximate line rating in MW using current results
#         p_flow_mw = abs(net.res_line.at[line_idx, "p_from_mw"])
#         overload_frac = (loading - threshold) / max(loading, 1e-6)

#         overload_mw = overload_frac * p_flow_mw * safety_margin

#         if overload_mw <= 0:
#             continue

#     # PTDF inclusion

#         if ptdf is not None:
#             sensitivity = ptdf[line_idx, bus]
#         else:
#             sensitivity = 0.05

#         if abs(sensitivity) > 1e-3:
#             continue

#         # Required BESS power for this line
#         required_mw = overload_mw / sensitivity
#         required_mw = np.sign(sensitivity) * overload_mw / abs(sensitivity)

#         p_actual_total += required_mw

#         detail.append(
#             { "line": line_idx,
#              "loading_pct": loading,
#              "overload_mw": overload_mw,
#              "ptdf": sensitivity,
#              "p_req_line": required_mw }
#         )

#     #sanity clamp
#     if not np.isfinite(p_actual_total):
#         p_actual_total = 0.0

#     return p_actual_total, {
#         "congested": True,
#         "lines": detail,
#         "p-bess_request_mw": p_actual_total,
#     }


### USED TO DISPATCH BESS ####
def dispatch_bess(battery, requested_mw, timestep_hrs=1.0, allow_charge=True):

    if battery is None:
        return {
            "requested_mw": 0.0,
            "actual_mw": 0.0,
            "soc_mwh": None,
            "soc_percent": None,
        }

    if timestep_hrs <= 0:
        raise ValueError("timestep_hours must be > 0")

    # enforce charging policy
    p_req = float(requested_mw)
    q_req = 0.2
    if not allow_charge and p_req < 0:
        p_req = 0.0

    # delegate limits to BatteryModel2
    actual_mw = battery.dispatch(
        p_set_mw=p_req,
        q_support=q_req,
        timestep_hours=timestep_hrs,
    )
    soc = battery.soc

    soc_mwh = battery.energy_current
    soc_percent = 100.0 * soc if soc is not None else None

    return {
        "requested_mw": requested_mw,
        "actual_mw": actual_mw,
        "soc_mwh": soc_mwh,
        "soc_percent": soc_percent,
    }


#### Third RUN POWER FLOW USING DIFFERENT METHOD OF COMPUTING REQUIRED RELIEF AND BATTERY DISPATCH #####
def run_powerflow(
    net,
    load_data,
    sgen_data,
    load_list,
    sgen_list,
    load_map,
    sgen_map,
    result_file="results",
    timestep_hrs = 1.0,
    overload_threshold=80,
    ):

    if not os.path.exists(result_file):
        os.makedirs(result_file)

    # determine timesteps from the time-series df (prefer load df if present)
    if load_data is not None and not load_data.empty:
        steps = len(load_data)
    elif sgen_data is not None and not sgen_data.empty:
        steps = len(sgen_data)
    else:
        raise ValueError("No time series data provided for loads or PV.")

    timesteps = range(steps)

    # power flow results list
    bess_pool = {}
    bus_results = []
    line_results = []

    bus_results_ctrl = []
    line_results_ctrl = []
    bus_dispatch = {}

    # controlled_overloadlines = [47, 52, 136, 20, 74, 246, 10, 44, 213, 266, 242, 140, 49, 53]
    # Bess_bus_line = {47: 30, 53: 40, 136: 35, 20: 27, 74: 89,
    #                  246: 32, 10: 19, 44: 26, 213: 58, 266: 190, 140: 222, 49: 75, 52: 24}

    # #used_buses =set()


    # battery log
    log_path = os.path.join(result_file, "battery_dispatch_log.csv")
    with open(log_path, "w", newline="") as f:
        csv.writer(f).writerow(
            ["timestep", "bus", "dispatch_mw", "soc_mwh"]
        )
    # logging.basicConfig(
    # filename= "battery_dispatch.log",
    # filemode= "a",
    # level= logging.INFO,
    # format= "%(asctime)s, %(message)s")

    # logger = logging.getLogger(__name__)

    Scaled_load = 4.0

    for t in timesteps:
        # assign load and PV generation
        for i in load_list:
            if i in load_map and load_map[i] in load_data.columns:
                val = pd.to_numeric(load_data.iloc[t][load_map[i]], errors="coerce")
                if pd.isna(val):
                    val = 0.0
                net.load.at[i, "p_mw"] = Scaled_load * float(val)
            else:
                net.load.at[i, "p_mw"] = 0.0

        # assign sgen (PV/wind) values per mapping
        for i in sgen_list:
            if i in sgen_map and sgen_map[i] in sgen_data.columns:
                val = pd.to_numeric(sgen_data.iloc[t][sgen_map[i]], errors="coerce")
                if pd.isna(val):
                    val = 0.0
                net.sgen.at[i, "p_mw"] = float(val)
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

        bus_row_Bctrl = {"timestep": t}
        for b in net.res_bus.index:
            bus_row_Bctrl[f"Bus_{b}_vm_pu"] = net.res_bus.at[b, "vm_pu"]
        bus_results.append(bus_row_Bctrl)

        line_row_Bctrl = {"timestep": t}
        for i in net.res_line.index:
            line_row_Bctrl[f"Line_{i}_loading%"] = net.res_line.at[i, "loading_percent"]
            line_row_Bctrl[f"Line_{i}_p_to_mw"] = net.res_line.at[i, "p_to_mw"]
        line_results.append(line_row_Bctrl)


    # 3. Detect overloaded lines
        overloaded_lines = detect_overloaded_lines(net, overload_threshold)

        # overloaded_lines = [i for i in all_overloaded_lines if i in controlled_overloadlines]

        #compute required relief
        if not overloaded_lines:
            relief_dict = {}
        else:
            relief_dict = compute_required_relief(
            net, overloaded_lines, overload_threshold)

        #if no overload charge battery
        if not relief_dict:
            for batt in bess_pool.values():
                dispatch_bess(
                    batt,
                    requested_mw=-0.2 * batt.power_limit,
                    timestep_hrs=timestep_hrs,
                )
            try:
                pp.runpp(net)
            except:
                pass
        else:
            for line_idx, required_mw in relief_dict.items():
                p_from = net.res_line.at[line_idx, "p_from_mw"]
                p_to   = net.res_line.at[line_idx, "p_to_mw"]

                if abs(p_from) > abs(p_to):
                    bus = int(net.line.at[line_idx, "from_bus"])
                else:
                    bus = int(net.line.at[line_idx, "to_bus"])


                bus_dispatch[bus] = bus_dispatch.get(bus, 0.0) + required_mw
                # if line_idx not in Bess_bus_line:
                #     continue
                # bus = Bess_bus_line[line_idx]

                # if bus is None or bus in used_buses:
                #     continue
            for bus, total_mw in bus_dispatch.items():

                if bus not in bess_pool:
                    bess_pool[bus] = BatteryModel(
                        net=net,
                        bess_bus=bus,
                        power_limit_mw=150.0,
                        energy_mwh=450.0,
                        soc_initial=0.9,
                        soc_min=0.05,
                        soc_max=0.95,
                    )
                dispatch_bess(
                    bess_pool[bus],
                    requested_mw=total_mw,
                    timestep_hrs=timestep_hrs,
                )

            #run power flow
            try:
                pp.runpp(net)
            except pp.LoadflowNotConverged:
                print(f"[t={t}] Controlled PF did not converge")

            bus_row_ctrl = {"timestep":t}
            for b in net.res_bus.index:
                bus_row_ctrl[f"Bus_{b}_vm_pu"] = net.res_bus.at[b, "vm_pu"]
            bus_results_ctrl.append(bus_row_ctrl)

            line_row_ctrl = {"timestep": t}
            for i in net.res_line.index:
                line_row_ctrl[f"Line_{i}_loading%"] = net.res_line.at[i, "loading_percent"]
                line_row_ctrl[f"Line_{i}_p_to_mw"] = net.res_line.at[i, "p_to_mw"]
            line_results_ctrl.append(line_row_ctrl)

            # log battery
            with open(log_path, "a", newline="") as f:
                w =  csv.writer(f)
                for bus, batt in bess_pool.items():
                    p = 0.0
                    try:
                        p = float(net.sgen.at[batt.bess_index, "p_mw"])
                    except Exception:
                        p = 0.0
                    w.writerow([t, bus, p, getattr(batt, "energy_current", getattr(batt, "soc", None))])


    #____save results___
    # before Control
    bus_results_df = pd.DataFrame(bus_results)
    line_results_df = pd.DataFrame(line_results)

    bus_results_df.to_csv(os.path.join(result_file, "bus_results_Bctrl.csv"))
    line_results_df.to_csv(os.path.join(result_file, "line_results_Bctrl.csv"))

    #After control
    bus_df = pd.DataFrame(bus_results_ctrl)
    line_df = pd.DataFrame(line_results_ctrl)

    bus_df.to_csv(os.path.join(result_file, "bus_results_ctrl.csv"))
    line_df.to_csv(os.path.join(result_file, "line_results_ctrl.csv"))


    print(f"[PPF2] Completed {steps} timesteps. Logs at {result_file}")


### THIRD APPROACH ###
###### PTDF-Based Coordinated Multi-BESS Dispatch Congestion ManagementPTDF-Based -##
#### --- Coordinated Multi-BESS Dispatch Congestion Management ####


def compute_ptdf(
    net,
    bess_buses,
):
    """
    Compute DC PTDFs using pandapower automatic slack balancing

    """
    #    run base DC power flows
    pp.rundcpp(net)
    base_flows = net.res_line.p_from_mw.copy()

    ptdf = {}
    delta_p = 1.0  # MW injection

    for line_indx, bus in bess_buses.items():

        # find sgen at this bus
        sgen_idx = net.sgen.index[net.sgen.bus == bus]
        if len(sgen_idx) == 0:
            continue
        sgen_idx = sgen_idx[0]

        # inject +1 MW
        net.sgen.at[sgen_idx, "p_mw"] += delta_p

        # dc power fow
        pp.rundcpp(net)

        # compute ptdf
        for line_indx in net.line.index:
            delta = net.res_line.at[line_indx, "p_from_mw"] - base_flows.at[line_indx]

            ptdf[(line_idx, bus)] = float(delta)

        # roll back injections
        net.sgen.at[sgen_idx, "p_mw"] -= delta_p

    return ptdf


def dispatch_multi_bess(
    net,
    bess_pool,
    ptdf,
    congested_lines,
    overload_threshold,
    timestep_hrs,
):

    total_dispatched = 0.0
    congested = False
    details = []

    for line_idx in congested_lines:

        loading = net.res_line.at[line_idx, "loading_percent"]
        if loading <= overload_threshold:
            continue  ## skip lines under threshold

        # congested = True

        # Required MW relief on the line
        pflow_mw = abs(net.res_line.at[line_idx, "p_from_mw"])
        overload_mw = max(
            0.0, (loading - overload_threshold) / overload_threshold * pflow_mw
        )

        if overload_mw <= 0:
            continue

        # congested = True

        relieved_mw = 0.0

        # PTDF sensitivities to each BESS
        sensitivities = {
            bus: ptdf.get((line_idx, bus), 0.0)
            for bus in bess_pool
            if abs(ptdf.get((line_idx, bus), 0.0)) > 1e-3
        }

        if not sensitivities:
            congested = True
            continue

        # Sort BESS by effectiveness (|PTDF| descending)

        sorted_bess = sorted(
            sensitivities.items(), key=lambda x: abs(x[1]), reverse=True
        )

        #  total_weight = sum(abs(s) for s in sensitivities.values())

        # Dispatch each BESS proportionally
        for bus, sensitivity in sorted_bess:
            bess = bess_pool[bus]

            remains_relief = overload_mw - abs(relieved_mw)
            if remains_relief <= 1e-3:
                break
            # K = 4
            direction = -np.sign(sensitivity)
            p_req = direction * (remains_relief / abs(sensitivity))

            p_act = bess.dispatch(
                p_set_mw=p_req, q_support=0.0, timestep_hours=timestep_hrs
            )

            relief = sensitivity * p_act

            relieved_mw += abs(sensitivity * p_act)

            total_dispatched += abs(p_act)

            details.append(
                {
                    "line": line_idx,
                    "bus": bus,
                    "ptdf": sensitivity,
                    "p_req": p_req,
                    "p_act": p_act,
                    "relief_mw": relief,
                    "soc": bess.soc,
                }
            )

        # Check if congestion fully relieved
        if abs(relieved_mw) < 0.98 * overload_mw:
            congested = True

    return total_dispatched, {
        "congested": congested,
        "details": details,
    }


# calculate mean, min and max %
def stat_result(file_path1, file_path2, file_path3, result_file="results"):
    bus_res_df = pd.read_csv(file_path1)
    line_loading_res_df = pd.read_csv(file_path2)
    trafo_loading_res_df = pd.read_csv(file_path3)

    # identify useful columns
    bus_cols = [c for c in bus_res_df.columns if "vm_pu" in c]

    if not bus_cols:
        print(" No 'vm_pu' columns found in:", bus_res_df.columns.tolist())
        return

    line_load_cols = [c for c in line_loading_res_df.columns if "loading%" in c]
    if not line_load_cols:
        print(" No 'loading%' columns found in:", line_loading_res_df.columns.tolist())
        return

    trafo_load_cols = [c for c in trafo_loading_res_df.columns if "loading%" in c]
    if not trafo_load_cols:
        print(" No 'loading%' columns found in:", trafo_loading_res_df.columns.tolist())
        return

    # Compute statistics
    bus_stats = bus_res_df[bus_cols].agg(["mean", "min", "max"]).transpose()
    # Drop any summary row accidentally included
    bus_stats.index = [
        int(re.search(r"\d+", c).group()) if re.search(r"\d+", c) else i
        for i, c in enumerate(bus_stats.index)
    ]
    bus_stats = bus_stats.iloc[:-1, :]
    # Rename columns for clarity
    bus_stats.columns = ["mean_vm_pu", "min_vm_pu", "max_vm_pu"]
    bus_stats.to_csv(os.path.join(result_file, "bus_statsB.csv"))

    line_stats = (
        line_loading_res_df[line_load_cols].agg(["mean", "min", "max"]).transpose()
    )
    line_stats.index = [
        int(re.search(r"\d+", c).group()) if re.search(r"\d+", c) else i
        for i, c in enumerate(line_stats.index)
    ]

    line_stats = line_stats.iloc[:, :]
    # Rename columns for clarity
    line_stats.columns = ["mean_loading%", "min_loading%", "max_loading%"]
    line_stats.to_csv(os.path.join(result_file, "line_statsB.csv"))

    trafo_stats = (
        trafo_loading_res_df[trafo_load_cols].agg(["mean", "min", "max"]).transpose()
    )
    trafo_stats.index = [
        int(re.search(r"\d+", c).group()) if re.search(r"\d+", c) else i
        for i, c in enumerate(trafo_stats.index)
    ]

    trafo_stats = trafo_stats.iloc[:, :]
    # Rename columns for clarity
    trafo_stats.columns = ["mean_loading%", "min_loading%", "max_loading%"]
    trafo_stats.to_csv(os.path.join(result_file, "trafo_statsB.csv"))

    return bus_stats, line_stats, trafo_stats


if __name__ == "__main__":

    # File paths
    base_path = "Substation/data_Pandapower.xlsx"
    Gen_file = "timeseriesdata/HS_Aggregierte_Erzeuger_2030.csv"
    Load_file = "timeseriesdata/HS_Aggregierte_Verbraucher_2030.csv"

    # Load input data
    Gen_data = pd.read_csv(Gen_file)  # assumed column: p_mw
    Load_data = pd.read_csv(Load_file)  # assumed column: p_mw

    # Build static network
    net = build_network(base_path)

    # conjested lines
    # critical_lines = [47, 52, 136, 20, 74, 246, 10, 44, 213, 266, 242, 140, 49, 53]

    # bess_buses = set()

    # for line in critical_lines:
    #     bess_buses.add(net.line.at[line, "from_bus"])
    #     bess_buses.add(net.line.at[line, "to_bus"])

    # Bess locations
    # overload_threshold = 80

    # overloaded_lines = detect_overloaded_lines(net, overload_threshold)

    bess_buses = {
        38: 130,
        189: 258,
        237: 248,
        204: 199,
        199: 115,
        206: 249,
        200: 118,
        39: 167,
        105: 134,
        40: 174,
        72: 49,
        278: 258,
    }
    # 278: 258,
    #     197: 254,
    #     42: 89,
    #     72: 49,
    #     70: 186,
    #     223: 85,
    #     105: 134,
    #     71: 126,
    #     40: 274,
    #     278: 250,
    #     126: 195,
    # 229: 89,
    # 230: 89,
    # create bess
    bess_pool = {}

    for line_idx, bus in bess_buses.items():
        bess_pool[bus] = BatteryModel(
            net=net,
            bess_bus=bus,
            power_limit_mw=250.0,
            energy_mwh=1000.0,
            soc_initial=0.80,
            soc_min=0.20,
            soc_max=0.95,
            name=f"BESS_{bus}",
        )

    # ptdf = {
    #     (209, 43): 0.4,
    #     (53, 40): 0.5,
    #     (136, 35): 0.3,
    #     (197, 254): 0.5,
    #     (74, 89): 0.5,
    #     (246, 32): 0.5,
    #     (189, 194): 0.6,
    #     (44, 26): 0.5,
    #     (212, 58): 0.4,
    #     (210, 42): 0.6,
    #     (224, 126): 0.4,
    #     (106, 189): 0.5,
    #     (52, 24): 0.6,
    #     (55, 40): 0.4,
    #     (50, 158): 0.5
    # }

    # ptdf = compute_ptdf(net, bess_buses)

    # for bus, bess in bess_pool.items():
    #     print(bus, ptdf.get((line_idx, bus), 0.0))

    # # Attach PV and Load time series
    # load_list, sgen_list = Load_timeseriesdata(net, base_path)

    load_list, sgen_list, load_ts_df, sgen_ts_df, sgen_map, load_map = (
        Load_timeseriesdata(net, base_path, sgen_csv=Gen_file, load_csv=Load_file)
    )

    # Run time-series power flow
    run_powerflow(
        net=net,
        load_data=Load_data,
        sgen_data=Gen_data,
        load_list=load_list,
        sgen_list=sgen_list,
        load_map=load_map,
        sgen_map=sgen_map,
        bess_pool=bess_pool,
        result_file="results",
    )

    # # cal stats
    # stat_result(
    #     "results/bus_results_Bctrl.csv",
    #     "results/line_results_Bctrl.csv",
    #     "results/trafo_results_Bctrl.csv",
    #     result_file="results",
    # )
