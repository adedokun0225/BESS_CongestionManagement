import pandas as pd


def detect_overload(
    file_path,
    threshold=80,
    overload_file="results/overload_lineB.csv",
    overload_file1="results/overload_trafoB.csv",
):

    overload_result = pd.read_csv(file_path)
    overload_result1 = pd.read_csv(file_path1)
    overload_rows = overload_result[overload_result["max_loading%"] > threshold]
    overload_rows1 = overload_result1[overload_result1["max_loading%"] > threshold]

    # return overload_rows

    if not overload_rows.empty or overload_rows1.empty:
        overload_rows.to_csv(overload_file, index=False)
        overload_rows1.to_csv(overload_file1, index=False)
        print(f"Overloads detected and saved to {overload_file}")
        print(f"Overloads detected and saved to {overload_file1}")
    else:
        print("No overloads detected.")


if __name__ == "__main__":
    file_path = "results/line_statsB.csv"
    file_path1 = "results/trafo_statsB.csv"

    detect_overload(
        file_path,
        threshold=80,
        overload_file="results/overload_lineB.csv",
        overload_file1="results/overload_trafoB.csv",
    )
