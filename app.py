import streamlit as st
import pandas as pd
import numpy as np

# =====================
# Load Data
# =====================
@st.cache_data
def load_data():
    # Corrected: Changed to pd.read_csv as the provided file is a CSV
    df = pd.read_csv("Pack_calculations.xlsx - Pack_optimisation.csv")
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

# Corrected: Moved energy_required_kwh calculation into the same if/else block
# to ensure variables are always defined based on application_type
if application_type == "EV":
    km_expected = st.sidebar.number_input("Km Expected per Charge", min_value=1)
    # Simple assumption: 150 Wh/km for EV
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

# Apply cell type filter if specified
if cell_type_input:
    candidate_cells = candidate_cells[candidate_cells['Cell Name'].str.contains(cell_type_input, case=False, na=False)]
    if candidate_cells.empty:
        st.warning(f"No cells found matching '{cell_type_input}'. Showing all available cells based on chemistry filter.")
        # Revert filter if no match, then apply chemistry if not 'Any'
        candidate_cells = df.copy()
        if cell_chemistry != "Any":
            candidate_cells = candidate_cells[candidate_cells['Chemistry'] == cell_chemistry]
else:
    # Apply chemistry filter if not 'Any'
    if cell_chemistry != "Any":
        candidate_cells = candidate_cells[candidate_cells['Chemistry'] == cell_chemistry]

# Check if any cells remain after filtering
if candidate_cells.empty:
    st.error("No cells found matching your selected criteria (chemistry/cell type). Please adjust your filters.")
    st.stop() # Stop execution if no cells are available

# Prioritize higher cycle life for selection
candidate_cells = candidate_cells.sort_values(by="Cycle life at 1C", ascending=False)

# =====================
# Packing Function
# =====================
def can_fit(cell, series, parallel, usable_l, usable_b, usable_h):
    """
    Checks if a given cell configuration (series, parallel) can fit within
    the usable dimensions, considering different orientations.
    Returns the fitting dimensions (l, b, h) if a fit is found, otherwise None.
    """
    if cell['Shape'] == 'Cylindrical':
        d = cell['Cell Diameter/Cell Length (mm)']
        h = cell['Cell height (mm)']
        # For cylindrical cells, assume diameter is length/breadth in 2D plane
        # and height is the third dimension. Consider rotations.
        volume_configurations = [
            (d * series, d * parallel, h), # Series along L, Parallel along B, Height along H
            (d * parallel, d * series, h), # Parallel along L, Series along B, Height along H
            (h, d * series, d * parallel), # Height along L, Series along B, Parallel along H
            (d * series, h, d * parallel), # Series along L, Height along B, Parallel along H
            (d * parallel, h, d * series), # Parallel along L, Height along B, Series along H
            (h, d * parallel, d * series), # Height along L, Parallel along B, Series along H
        ]
    else:  # Prismatic
        l = cell['Cell Diameter/Cell Length (mm)'] # Assuming this is length for prismatic
        b = cell['Third dimension (mm)']  # Assuming this is breadth for prismatic
        h = cell['Cell height (mm)']
        # For prismatic cells, consider all 6 permutations of (l*series, b*parallel, h)
        # and their rotated versions.
        volume_configurations = [
            (l * series, b * parallel, h),
            (l * series, h, b * parallel),
            (b * parallel, l * series, h),
            (b * parallel, h, l * series),
            (h, l * series, b * parallel),
            (h, b * parallel, l * series),
        ]

    for config in volume_configurations:
        # Check if the current configuration fits within the usable space
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
    # Calculate cell energy in kWh
    cell_wh = cell['Nominal Voltage (V)'] * cell['Cell Capacity (Ah)'] / 1000

    # Handle potential division by zero if cell_wh is 0
    if cell_wh == 0:
        continue # Skip this cell if it has no energy capacity

    # Calculate required parallel and series connections
    parallel = int(np.ceil(energy_required_kwh / cell_wh))
    series = int(np.ceil(expected_voltage / cell['Nominal Voltage (V)']))

    # Ensure at least 1 parallel and 1 series cell
    if parallel == 0: parallel = 1
    if series == 0: series = 1

    total_cells = series * parallel

    # Check if the calculated pack configuration fits
    fit = can_fit(cell, series, parallel, usable_l, usable_b, usable_h)
    if fit:
        best_cell = cell
        fit_dims = fit
        break # Found a suitable cell, stop searching

if best_cell is not None:
    st.success(f"Selected Cell: {best_cell['Cell Name']} ({best_cell['Chemistry']})")

    # Calculate pack specifications
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
        # Corrected column name for pack energy density
        "Pack Energy Density (Wh/kg)": round(best_cell['Wh/kg (pack) (cells + 30%)'], 2),
        "Cycle Life": int(best_cell['Cycle life at 1C'])
    }

    st.subheader("Battery Pack Specifications")
    # Display pack specifications in a readable format
    for k, v in pack_specs.items():
        st.write(f"**{k}:** {v}")
else:
    st.error("No suitable cell found that fits within the available space or meets energy requirements. Try different dimensions, lower energy requirements, or adjust cell filters.")

# =====================
# Raw Data Option
# =====================
with st.expander("See Available Cells Considered"):
    # Display relevant columns from the candidate cells dataframe
    st.dataframe(candidate_cells[[
        'Cell Name', 'Chemistry', 'Nominal Voltage (V)', 'Cell Capacity (Ah)',
        'Cycle life at 1C', 'Wh/kg (pack) (cells + 30%)' # Corrected column name here too
    ]])
