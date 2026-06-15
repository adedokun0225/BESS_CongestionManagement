
import pandas as pd 
import matplotlib.pyplot as plt 
from seaborn._core.properties import LineWidth

#load datatset

gen_file = "timeseriesdata/HS_Aggregierte_Erzeuger_2030.csv"
load_file = "timeseriesdata/HS_Aggregierte_Verbraucher_2030.csv"

gen = pd.read_csv(gen_file)
load = pd.read_csv(load_file)

print("Gen dataset shape:", gen.shape)
print("Load dataset shape:", load.shape)    
    
#Aggregate across all substation
gen_total = gen.sum(axis=1)
load_total = load.sum(axis=1)

#compute statistical summary
summ_table = pd.DataFrame({
    "min (MW)": [load_total.min(), gen_total.min()],
    "max(mw)": [load_total.max(), gen_total.max()],
    "mean(mw)": [load_total.mean(), gen_total.mean()],
    "std Dev(mw)": [load_total.std(), gen_total.std()],
    "95th Percentile (mw)": [load_total.quantile(0.95), gen_total.quantile(0.95)],
    "Annual Energy (MWh)": [load_total.sum(), gen_total.sum()]
}, index=["Total Load", "Total gen"])

print("\n===== Statistical Summary Table (System-Level) =====\n")
print(summ_table)

summ_table.to_csv("results/Statistical_Summary_Table.csv")

# compute net surplus Gen-load
net_surplus = gen_total - load_total

#Plot full-year profiles (8760 hrs)
plt.figure(figsize=(12, 6))

plt.plot(load_total, label="Total load (MW)")
plt.plot(gen_total, label="Total Generation (MW)")

plt.xlabel("Hour of Year")
plt.ylabel("Power(MW)")
plt.title("Total Load and Generation Profiles (8760 Hours)")
plt.legend()
plt.grid(True)
plt.show()

# plt.savefig("Total_profile_8760hrs.png", dpi=600)

#plot first-week zoom (168 hrs)
plt.figure(figsize=(12, 6))

plt.plot(load_total[:168], label="Total Load (MW)")
plt.plot(gen_total[:168], label="Total Generation (MW)")

plt.xlabel("Hrs")
plt.ylabel("Power (MW)")
plt.title("Total Load and Generation profiles (First week zoom)")
plt.legend()
plt.grid(True)
plt.show()

# plt.savefig("Total_profile_FirstWeek.png", dpi=600)


# plot net surplud profile
plt.figure(figsize=(12, 6))
plt.plot(net_surplus, linewidth=1)

plt.title("Net Surplus Profile(Gen - load) - Full Year")
plt.xlabel("Hour of the Year")
plt.ylabel("Net Surplus (MW)")

# plt.axhline(0, linestyle="--", LineWidth=2)
plt.legend()
plt.grid(True)
plt.show()


#Plot net surplus profile (first week)
plt.figure(figsize=(12, 6))
plt.plot(net_surplus[:168], LineWidth=1)

plt.title("Net Surplus Profile (Generation - Load) - First Week")
plt.xlabel("Hour of week")
plt.ylabel("Net Surplus (MW)")

# plt.axhline(0, linestyle="--", LineWidth=1)
plt.legend()
plt.grid(True)
plt.show()

# #save net surplus to CSV
# net_surplus.to_csv("Net_Surplus_Profile.csv", index=False)


