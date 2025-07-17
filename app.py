import streamlit as st
import pandas as pd
import numpy as np

# =====================
# Load Data
# =====================
@st.cache_data
def load_data():
    file_path = "Pack_calculations.csv"
    # Define common encodings and separators to try
    possible_encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
    possible_seps = [',', ';', '\t'] # Comma, Semicolon, Tab

    df = None
    st.info("Attempting to load data with various encoding and separator combinations...")

    # Iterate through possible encodings
    for encoding in possible_encodings:
        # Iterate through possible separators
        for sep in possible_seps:
            # Try with C engine first (faster, but less flexible)
            try:
                # on_bad_lines='warn' is crucial here: it logs problematic lines instead of crashing
                df = pd.read_csv(file_path, encoding=encoding, sep=sep, engine='c', on_bad_lines='warn', skipinitialspace=True)
                # Basic validation: check if DataFrame is not empty and has a reasonable number of columns
                if not df.empty and len(df.columns) > 5 and 'Cell Name' in df.columns:
                    st.success(f"Data successfully loaded with encoding '{encoding}' and separator '{sep}' (C engine).")
                    return df
                else:
                    # If it loaded but looks malformed (e.g., single column, missing key column), try next
                    st.warning(f"Loaded with '{encoding}' and '{sep}' (C engine), but data looks incomplete. Trying other options.")
                    df = None # Reset df to ensure next attempt is fresh
            except (UnicodeDecodeError, pd.errors.ParserError, KeyError) as e:
                # Catch specific errors and continue to the next combination
                # KeyError might occur if the header isn't parsed correctly and a critical column is missing
                # st.info(f"Attempt with encoding '{encoding}', separator '{sep}' (C engine) failed: {e}")
                pass # Fail silently and try next combination

            # If C engine failed or produced sparse data, try Python engine (more robust, but slower)
            try:
                df = pd.read_csv(file_path, encoding=encoding, sep=sep, engine='python', on_bad_lines='warn', skipinitialspace=True)
                if not df.empty and len(df.columns) > 5 and 'Cell Name' in df.columns:
                    st.success(f"Data successfully loaded with encoding '{encoding}' and separator '{sep}' (Python engine).")
                    return df
                else:
                    st.warning(f"Loaded with '{encoding}' and '{sep}' (Python engine), but data looks incomplete. Trying other options.")
                    df = None
            except (UnicodeDecodeError, pd.errors.ParserError, KeyError) as e:
                # st.info(f"Attempt with encoding '{encoding}', separator '{sep}' (Python engine) failed: {e}")
                pass

    # If all attempts fail, display a comprehensive error message and stop the app
    st.error(
        "**Failed to load data!** "
        "The CSV file 'Pack_calculations.xlsx - Pack_optimisation.csv' could not be parsed "
        "despite multiple robust attempts. This usually means the file has fundamental "
        "formatting issues such as: \n"
        "1. **Inconsistent number of columns** in different rows.\n"
        "2. **Unusual delimiters** not covered by comma, semicolon, or tab.\n"
        "3. **Special characters** that are not properly escaped.\n\n"
        "**Recommendation:** Please open the CSV file in a plain text editor (like Notepad, VS Code, Sublime Text) "
        "or a spreadsheet program (like Excel, Google Sheets). Inspect it carefully for any "
        "irregularities. A common fix is to re-save the file explicitly as 'Comma Separated Values (.csv)' "
        "from your spreadsheet software, ensuring all data is consistent."
    )
    st.stop() # Stop the app execution if data loading fails

df = load_data()

# =====================
# User Inputs
# =====================
st.title("Battery Pack Design Calculator")

st.sidebar.header("Application & Load Requirements")
application_type = st.sidebar.selectbox("Select Application Type", ["EV", "Stationary Storage"])
expected_voltage = st.sidebar.number_input("Expected Voltage (V)", min_value=12)

cell_chemistry = st.sidebar.selectbox("Choose Preferred Chemistry (Optional)", ["Any", "LFP", "NMC", "LTO"])
cell_type_input = st.sidebar.text_input("Choose Cell Type (Optional)", help="Leave blank to let system auto-select best fit")

if application_type == "EV":
    km_expected = st.sidebar.number_input("Km Expected per Charge", min_value=1)
    energy_required_kwh = (km_expected * 33) / 1000
else:
    hours_backup = st.sidebar.number_input("Backup Hours Required", min_value=1.0)
    total_watt_load = st.sidebar.number_input("Total Load (W)", min_value=0.1)
    energy_required_kwh = (hours_backup * total_watt_load) / 1000

st.sidebar.header("Space Constraints (mm)")
avail_l = st.sidebar.number_input("Length Available", min_value=100)
avail_b = st.sidebar.number_input("Breadth Available", min_value=100)
avail_h = st.sidebar.number_input("Height Available", min_value=100)

# =====================
# Derived Calculations
# =====================
tolerance = 5  # mm on each side for packing and connections
usable_l = avail_l - 2 * tolerance
usable_b = avail_b - 2 * tolerance
usable_h = avail_h - 2 * tolerance

# =====================
# Filter Candidates
# =====================
candidate_cells = df.copy()

if cell_type_input:
    # Use .astype(str) to ensure comparison with string, handling potential mixed types
    candidate_cells = candidate_cells[candidate_cells['Cell Name'].astype(str).str.contains(cell_type_input, case=False, na=False)]
    if candidate_cells.empty:
        st.warning(f"No cells found matching '{cell_type_input}'. Showing all available cells based on chemistry filter.")
        candidate_cells = df.copy()
        if cell_chemistry != "Any":
            candidate_cells = candidate_cells[candidate_cells['Chemistry'] == cell_chemistry]
else:
    if cell_chemistry != "Any":
        candidate_cells = candidate_cells[candidate_cells['Chemistry'] == cell_chemistry]

if candidate_cells.empty:
    st.error("No cells found matching your selected criteria (chemistry/cell type). Please adjust your filters.")
    st.stop()

# Ensure 'Cycle life at 1C' is numeric before sorting
candidate_cells['Cycle life at 1C'] = pd.to_numeric(candidate_cells['Cycle life at 1C'], errors='coerce').fillna(0)

candidate_cells = candidate_cells.sort_values(by="Cycle life at 1C", ascending=False)

# =====================
# Packing Function
# =====================
def can_fit(cell, series, parallel, usable_l, usable_b, usable_h):
    # Ensure all dimensions are numeric, coercing errors to NaN and filling with a default (e.g., 0)
    # This prevents potential TypeError if a dimension column contains non-numeric data
    cell_diameter_length = pd.to_numeric(cell['Cell Diameter/Cell Length (mm)'], errors='coerce')
    cell_diameter_length = 0 if pd.isna(cell_diameter_length) else cell_diameter_length


    cell_height = pd.to_numeric(cell['Cell height (mm)'], errors='coerce')
    cell_height = 0 if pd.isna(cell_height) else cell_height

    third_dimension = pd.to_numeric(cell['Third dimension (mm)'], errors='coerce')
    third_dimension = 0 if pd.isna(third_dimension) else third_dimension


    if cell['Shape'] == 'Cylindrical':
        d = cell_diameter_length
        h = cell_height
        volume_configurations = [
            (d * series, d * parallel, h),
            (d * parallel, d * series, h),
            (h, d * series, d * parallel),
            (d * series, h, d * parallel),
            (d * parallel, h, d * series),
            (h, d * parallel, d * series),
        ]
    else:  # Prismatic
        l = cell_diameter_length
        b = third_dimension
        h = cell_height
        volume_configurations = [
            (l * series, b * parallel, h),
            (l * series, h, b * parallel),
            (b * parallel, l * series, h),
            (b * parallel, h, l * series),
            (h, l * series, b * parallel),
            (h, b * parallel, l * series),
        ]

    for config in volume_configurations:
        if (config[0] <= usable_l and
            config[1] <= usable_b and
            config[2] <= usable_h):
            return config
    return None

# =====================
# Selection Logic
# =====================
best_cell = None
fit_dims = None
pack_specs = {}

for _, cell in candidate_cells.iterrows():
    # Ensure nominal voltage and cell capacity are numeric
    nominal_voltage = pd.to_numeric(cell['Nominal Voltage (V)'], errors='coerce')
    nominal_voltage = 0 if pd.isna(nominal_voltage) else nominal_voltage
    cell_capacity = pd.to_numeric(cell['Cell Capacity (Ah)'], errors='coerce')
    cell_capacity = 0 if pd.isna(cell_capacity) else cell_capacity
    cell_wh = nominal_voltage * cell_capacity / 1000

    if cell_wh <= 0: # Ensure cell has positive energy capacity
        continue

    parallel = int(np.ceil(energy_required_kwh/(expected_voltage*cell_capacity)))
    series = int(np.ceil(expected_voltage / nominal_voltage))

    if parallel <= 0: parallel = 1
    if series <= 0: series = 1

    total_cells = series * parallel

    fit = can_fit(cell, series, parallel, usable_l, usable_b, usable_h)
    if fit:
        best_cell = cell
        fit_dims = fit
        break

if best_cell is not None:
    st.success(f"Selected Cell: {best_cell['Cell Name']} ({best_cell['Chemistry']})")

    # Ensure all values used in pack_specs are numeric before rounding/displaying
    best_cell_nominal_voltage = pd.to_numeric(best_cell['Nominal Voltage (V)'], errors='coerce')
    best_cell_nominal_voltage = 0 if pd.isna(best_cell_nominal_voltage) else best_cell_nominal_voltage
    
    best_cell_capacity = pd.to_numeric(best_cell['Cell Capacity (Ah)'], errors='coerce')
    best_cell_capacity = 0 if pd.isna(best_cell_capacity) else best_cell_capacity
    
    best_cell_wh_per_kg_pack = pd.to_numeric(best_cell['Wh/kg (pack) (cells + 30%)'], errors='coerce')
    best_cell_wh_per_kg_pack = 0 if pd.isna(best_cell_wh_per_kg_pack) else best_cell_wh_per_kg_pack
    
    best_cell_cycle_life = pd.to_numeric(best_cell['Cycle life at 1C'], errors='coerce')
    best_cell_cycle_life = 0 if pd.isna(best_cell_cycle_life) else best_cell_cycle_life


    pack_specs = {
        "Required Energy (kWh)": round(energy_required_kwh, 2),
        "Cell Voltage (V)": best_cell_nominal_voltage,
        "Cell Capacity (Ah)": best_cell_capacity,
        "Series (#)": series,
        "Parallel (#)": parallel,
        "Total Cells": total_cells,
        "Pack Capacity (Ah)": round(parallel * best_cell_capacity, 2),
        "Pack Voltage (V)": round(series * best_cell_nominal_voltage, 2),
        "Pack Volume (mm)": f"{int(fit_dims[0])} x {int(fit_dims[1])} x {int(fit_dims[2])}",
        "Pack Energy Density (Wh/kg)": round(best_cell_wh_per_kg_pack, 2),
        "Cycle Life": int(best_cell_cycle_life)
    }

    st.subheader("Battery Pack Specifications")
    for k, v in pack_specs.items():
        st.write(f"**{k}:** {v}")
else:
    st.error("No suitable cell found that fits within the available space or meets energy requirements. Try different dimensions, lower energy requirements, or adjust cell filters.")

# =====================
# Raw Data Option
# =====================
with st.expander("See Available Cells Considered"):
    # Ensure columns are numeric for display if they contain non-numeric data
    display_df = candidate_cells[[
        'Cell Name', 'Chemistry', 'Nominal Voltage (V)', 'Cell Capacity (Ah)',
        'Cycle life at 1C', 'Wh/kg (pack) (cells + 30%)'
    ]].copy() # Use .copy() to avoid SettingWithCopyWarning

    # Convert potentially problematic columns to numeric, coercing errors
    for col in ['Nominal Voltage (V)', 'Cell Capacity (Ah)', 'Cycle life at 1C', 'Wh/kg (pack) (cells + 30%)']:
        display_df[col] = pd.to_numeric(display_df[col], errors='coerce')

    st.dataframe(display_df)
