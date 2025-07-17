import streamlit as st
import pandas as pd
import numpy as np

# =====================
# Load Data
# =====================
@st.cache_data
def load_data():
    # Corrected: Removed explicit delimiter=',' to let pandas infer,
    # as ParserError can occur with inconsistent delimiters.
    # Kept encoding and python engine for robustness.
    try:
        df = pd.read_csv("Pack_calculations.xlsx - Pack_optimisation.csv", encoding='utf-8', engine='python')
    except UnicodeDecodeError:
        # Fallback to 'latin1' if 'utf-8' fails
        df = pd.read_csv("Pack_calculations.xlsx - Pack_optimisation.csv", encoding='latin1', engine='python')
    except pd.errors.ParserError as e:
        st.error(f"Error parsing CSV file: {e}. Please ensure the file is correctly formatted and consistent (e.g., same number of columns per row).")
        st.stop() # Stop the app if parsing fails
    return df

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
    energy_required_kwh = (expected_voltage * km_expected * 0.15) / 1000
else:
    hours_backup = st.sidebar.number_input("Backup Hours Required", min_value=1.0)
    total_kw_load = st.sidebar.number_input("Total Load (kW)", min_value=0.1)
    energy_required_kwh = hours_backup * total_kw_load

st.sidebar.header("Space Constraints (mm)")
avail_l = st.sidebar.number_input("Length Available", min_value=100)
avail_b = st.sidebar.number_input("Breadth Available", min_value=100)
avail_h = st.sidebar.number_input("Height Available", min_value=100)

# =====================
# Derived Calculations
# =====================
tolerance = 15  # mm on each side for packing and connections
usable_l = avail_l - 2 * tolerance
usable_b = avail_b - 2 * tolerance
usable_h = avail_h - 2 * tolerance

# =====================
# Filter Candidates
# =====================
candidate_cells = df.copy()

if cell_type_input:
    candidate_cells = candidate_cells[candidate_cells['Cell Name'].str.contains(cell_type_input, case=False, na=False)]
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

candidate_cells = candidate_cells.sort_values(by="Cycle life at 1C", ascending=False)

# =====================
# Packing Function
# =====================
def can_fit(cell, series, parallel, usable_l, usable_b, usable_h):
    if cell['Shape'] == 'Cylindrical':
        d = cell['Cell Diameter/Cell Length (mm)']
        h = cell['Cell height (mm)']
        volume_configurations = [
            (d * series, d * parallel, h),
            (d * parallel, d * series, h),
            (h, d * series, d * parallel),
            (d * series, h, d * parallel),
            (d * parallel, h, d * series),
            (h, d * parallel, d * series),
        ]
    else:  # Prismatic
        l = cell['Cell Diameter/Cell Length (mm)']
        b = cell['Third dimension (mm)']
        h = cell['Cell height (mm)']
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
    cell_wh = cell['Nominal Voltage (V)'] * cell['Cell Capacity (Ah)'] / 1000

    if cell_wh == 0:
        continue

    parallel = int(np.ceil(energy_required_kwh / cell_wh))
    series = int(np.ceil(expected_voltage / cell['Nominal Voltage (V)']))

    if parallel == 0: parallel = 1
    if series == 0: series = 1

    total_cells = series * parallel

    fit = can_fit(cell, series, parallel, usable_l, usable_b, usable_h)
    if fit:
        best_cell = cell
        fit_dims = fit
        break

if best_cell is not None:
    st.success(f"Selected Cell: {best_cell['Cell Name']} ({best_cell['Chemistry']})")

    pack_specs = {
        "Required Energy (kWh)": round(energy_required_kwh, 2),
        "Cell Voltage (V)": best_cell['Nominal Voltage (V)'],
        "Cell Capacity (Ah)": best_cell['Cell Capacity (Ah)'],
        "Series (#)": series,
        "Parallel (#)": parallel,
        "Total Cells": total_cells,
        "Pack Capacity (Ah)": round(parallel * best_cell['Cell Capacity (Ah)'], 2),
        "Pack Voltage (V)": round(series * best_cell['Nominal Voltage (V)'], 2),
        "Pack Volume (mm)": f"{int(fit_dims[0])} x {int(fit_dims[1])} x {int(fit_dims[2])}",
        "Pack Energy Density (Wh/kg)": round(best_cell['Wh/kg (pack) (cells + 30%)'], 2),
        "Cycle Life": int(best_cell['Cycle life at 1C'])
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
    st.dataframe(candidate_cells[[
        'Cell Name', 'Chemistry', 'Nominal Voltage (V)', 'Cell Capacity (Ah)',
        'Cycle life at 1C', 'Wh/kg (pack) (cells + 30%)'
    ]])
