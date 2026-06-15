import os
import csv
import pandas as pd
import pandapower as pp
from BatteryModel2 import BatteryModel


def run_powerflow(
                net,
                load_data,
                sgen_data,
                load_list,
                sgen_list,
                load_map,
                sgen_map,
                result_file="results",
                overload_threshold=70,
                timestep_hours=1.0,
                virtual_bess_defaults=None
                ):
    
    # default Battery parameters
    if virtual_bess_defaults is None:
        virtual_bess_defaults = {}
        
    defaults = {
        "power_lim_mw": 10.0,
        "energy_mwh": 40.0,
        "soc_initial": 0.5,
        "name_prefix": "BESS"
    }
    defaults.update(virtual_bess_defaults)
    
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

    # Pool of BatteryModel instances keyed by bus index
    bess_pool = {}
    
    # Prepare logs
    log_path = os.path.join(result_file, "battery_dispatch_log.csv")
    with open(log_path, "w", newline="") as f:
        csv.writer(f).writerow(["timestep", "bus", "dispatch_mw", "soc_mwh"])
        
    bus_results = []
    line_results = []
    
    for t in timesteps:
        # assign load and PV generation
        for i in load_list:
            if i in load_map and load_map[i] in load_data.columns:
                val = pd.to_numeric(load_data.iloc[t][load_map[i]], errors="coerce")
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
            
            bus_results.append(pd.Series([pd.NA] * len(net.bus), index=net.bus.index, name=t))
            line_results.append(pd.Series([pd.NA] * len(net.line), index=net.line.index, name=t))
            
            continue
        
        # Detect overloaded lines 
        if "loaded_percent"in net.res_line.columns:
            overload_lines = net.res_line.index[net.res_line["loading_percent"] > overload_threshold].tolist()
        else:
            overload_lines = []
            
        if not overload_lines:
            # Mild charging behavior for existing batteries
            for bus, batt in bess_pool.items(): 
                # small charging setpoint (negative p -> charging)
                batt.dispatch(-0.1 * defaults["p_lim_mw"], timestep_hours)
            try:
                pp.runpp(net)
            except Exception:
                pass
        else:
            # for each overload lines compute required injection and aggregate per "to_bus"
            bus_needed = {}
            for i in overload_lines:
                try:
                    loading = float(net.res_line.at[i, "loading_percent"])
                    p_to = float(net.res_line.at[i, "power_lim_mw"])
                except Exception:
                    continue
                if loading <= overload_threshold:
                    continue
                # part of current p_to to remove
                frac = (loading - overload_threshold) / max(loading, 1e-9)
                used_mw = p_to * frac
                to_bus = int(net.line.at[i, "to_bus"])
                bus_needed[to_bus] = bus_needed.get(to_bus, 0.0) + used_mw
            
            # Ensure BatteryModel at bus and dispatch
            for bus, num in bus_needed.items():
                if bus not in bess_pool:
                    # create BatteryModel (it registers an sgen inside)
                    bess_pool[bus] = BatteryModel(
                        net=net,
                        bess_bus=bus,
                        power_limit_mw=defaults["p_lim_mw"],
                        energy_mwh=defaults["energy_mwh"],
                        soc_initial=defaults["soc_initial"],
                        name=f"{defaults['name_prefix']}_bus{bus}"
                    )
                batt = bess_pool[bus]
                desired_discharge = max(0.0, num)  # discharge only
                
                # BatteryModel.dispatch returns soc (or updates net.sgen)
                batt.dispatch(desired_discharge, timestep_hours)
                
                # Mild charging on Batteries not used
                for bus, batt in bess_pool.items():
                    if bus not in bus_needed:
                        batt.dispatch(-0.05 * defaults["p_lim_mw"], timestep_hours)
                        
                try:
                    pp.runpp(net)
                except Exception as e:
                    print(f"[t={t}] PF after dispatch failed: {e}")
                    # optional: scale back
                    
                # log battery dispatch states
            with open(log_path, "a", newline="") as f:
                writer = csv.writer(f)
                for bus, batt in bess_pool.items():
                    p = 0.0
                    try:
                        p = float(net.sgen.at[batt.bess_index, "p_mw"])
                    except Exception:
                        p = 0.0
                    writer.writerow([t, bus, p, getattr, (batt, "energy_current", getattr(batt, "soc", None))])   
                    
            # collect result    
            try:
                bus_results.append(net.res_bus["vm_pu"].copy().rename(t))
            except Exception:
                bus_results.append(pd.Series([pd.NA] * len(net.bus), index=net.bus.index, name=t))
            try:
                line_results.append(net.res_line["loading_percent"].copy().rename(t))
            except Exception:
                line_results.append(pd.Series([pd.NA] * len(net.line), index=net.line.index, name=t))
    
    # save results
    bus_df = pd.DataFrame(bus_results)
    line_df = pd.DataFrame(line_results)
    
    bus_df.to_csv(os.path.join(result_file, "bus_result.csv"))
    line_df.to_csv(os.path.join(result_file, "line_results.csv"))
    
    print(f"[PPF2] Completed {steps} timesteps. Logs at {result_file}")
    return bus_df, line_df, bess_pool
                        
                    
