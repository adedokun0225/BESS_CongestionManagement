import pandapower as pp


class BatteryModel:
    def __init__(
        self,
        net,
        bess_bus,
        power_limit_mw,
        energy_mwh,
        soc_initial=0.80,
        soc_min=0.20,
        bat_ch=0.98,
        bat_dis=0.98,
        soc_max=0.95,
        ramp_rate_mw_per_step=150.0,
        name="BESS",
    ):
        """
        net: pandapower network object
        bess_bus: bus location of battery
        power_limit_mw: max charge/discharge power
        energy_mwh: total energy capacity
        soc_initial: initial state of charge (0–1)
        """
        self.net = net
        self.bess_bus = bess_bus
        self.power_limit = abs(power_limit_mw)
        self.energy = energy_mwh
        self.soc = soc_initial
        self.soc_min = soc_min
        self.soc_max = soc_max
        self.bat_ch = bat_ch
        self.bat_dis = bat_dis
        # self.reserve_soc =reserve_soc
        self.energy_current = soc_initial * energy_mwh
        self.ramp_rate = ramp_rate_mw_per_step
        self.p_prev = 0.0

        # Battery instance creation
        self.bess_index = pp.create_sgen(
            net, bus=bess_bus, p_mw=0.0, q_mvar=0.0, name=name, in_service=True
        )

    def available_discharge_mw(self, timestep_hours):
        # MAx mw available for discharge given SOC
        usable_energy = max(0.0, (self.energy_current - (self.soc_min * self.energy)))

        return min(self.power_limit, usable_energy * self.bat_dis / timestep_hours)

    def available_charge_mw(self, timestep_hours):
        # MAx mw available for charge given SOC
        charge_energy = max(0.0, (self.soc_max * self.energy - self.energy_current))

        return min(self.power_limit, charge_energy / (timestep_hours * self.bat_ch))

    def dispatch(self, p_set_mw, q_support, timestep_hours=1.0):

        # Dispatch battery at a given power level (+ discharge, – charge)

        if timestep_hours <= 0:
            return 0.0
        # Ramp_rate limit
        p_actual = float(p_set_mw)
        p_actual = max(
            self.p_prev - self.ramp_rate, min(self.p_prev + self.ramp_rate, p_actual)
        )

        # Limit power
        p_actual = max(min(p_actual, self.power_limit), -self.power_limit)

        # SOC aware limit
        if p_actual > 0:  # discharge
            p_actual = min(p_actual, self.available_discharge_mw(timestep_hours))
        if p_actual < 0:  # charge
            p_actual = max(-self.available_charge_mw(timestep_hours), p_actual)

        # Update Energy
        if p_actual >= 0:  # discharge
            update_e = -p_actual * timestep_hours / self.bat_dis
        else:  # charge
            update_e = -p_actual * timestep_hours * self.bat_ch

        self.energy_current += update_e

        # clamp energy current
        self.energy_current = max(
            self.soc_min * self.energy,
            min(self.energy_current, self.soc_max * self.energy),
        )

        # Enforce SOC limits
        self.soc = self.energy_current / self.energy
        self.p_prev = p_actual

        # Apply dispatch into pandapower network
        self.net.sgen.at[self.bess_index, "p_mw"] = p_actual
        self.net.sgen.at[self.bess_index, "q_mvar"] = q_support

        return p_actual
