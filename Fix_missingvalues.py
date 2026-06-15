import pandas as pd


def fill_missing_after_with_before(before_file, after_file, output_file):
    # Load datasets
    before = pd.read_csv(before_file)
    after = pd.read_csv(after_file)

    # Ensure timestep column exists
    if "timestep" not in before.columns:
        before = before.rename(columns={before.columns[1]: "timestep"})
    if "timestep" not in after.columns:
        after = after.rename(columns={after.columns[1]: "timestep"})

    # Set timestep as index
    before = before.set_index("timestep")
    after = after.set_index("timestep")

    # Fill missing AFTER values with BEFORE values
    after_filled = after.combine_first(before)

    # Reset index
    after_filled = after_filled.reset_index()

    # Save corrected dataset
    after_filled.to_csv(output_file, index=False)

    print("Dataset corrected and saved to:", output_file)
    print("Total timesteps:", len(after_filled))


if __name__ == "__main__":

    fill_missing_after_with_before(
        "15 iterations/line_results_Bctrl.csv",  # before congestion results
        "15 iterations/line_results_ctrl.csv",  # after congestion results
        "15 iterations/line_results_ctrl_fixed.csv",
    )
