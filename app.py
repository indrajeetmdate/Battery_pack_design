import streamlit as st
import pandas as pd
import numpy as np

# =====================
# Load Data
# =====================
@st.cache_data
def load_data():
    df = pd.read_excel("Pack_calculations.xlsx")
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
else:
    hours_backup = st.sidebar.number_input("Backup Hours Required", min_value=1.0)
    total_kw_load = st.sidebar.number_input("Total Load (kW)", min_value=0.1)

st.sidebar.header("Space Constraints (mm)")
avail_l = st.sidebar.number_input("Length Available", min_value=100)
avail_b = st.sidebar.number_input("Breadth Available", min_value=100)
avail_h = st.sidebar.number_input("Height Available", min_value=100)

# =====================
# Derived Calculations
# =====================
tolerance = 15  # mm on each side
usable_l = avail_l - 2 * tolerance
usable_b = avail_b - 2 * tolerance
usable_h = avail_h - 2 * tolerance

if application_type == "EV":
    energy_required_kwh = (expected_voltage * km_expected * 0.15) / 1000  # Simple assumption: 150 Wh/km
else:
    energy_required_kwh = hours_backup * total_kw_load

# =====================
# Filter Candidates
# =====================
candidate_cells = df.copy()

if cell_type_input:
    candidate_cells = candidate_cells[candidate_cells['Cell Name'] == cell_type_input]
else:
    if cell_chemistry != "Any":
        candidate_cells = candidate_cells[candidate_cells['Chemistry'] == cell_chemistry]

# Prioritize higher cycle life
candidate_cells = candidate_cells.sort_values(by="Cycle life at 1C", ascending=False)

# =====================
# Packing Function
# =====================
def can_fit(cell, series, parallel):
    # Determine cell orientation dimensions
    if cell['Cell Shape'] == 'Cylindrical':
        d = cell['Diameter (mm)']
        h = cell['Height (mm)']
        volume_configurations = [
            (d * series, d * parallel, h),  # L x B x H
            (d * parallel, d * series, h),
            (h, d * series, d * parallel),
            (d * series, h, d * parallel),
        ]
    else:  # Prismatic
        l = cell['Length (mm)']
        b = cell['Breadth (mm)']
        h = cell['Height (mm)']
        volume_configurations = [
            (l * series, b * parallel, h),
            (b * parallel, l * series, h),
            (h, l * series, b * parallel),
        ]

    for config in volume_configurations:
        if all([config[0] <= usable_l, config[1] <= usable_b, config[2] <= usable_h]):
            return config
    return None

# =====================
# Selection Logic
# =====================
best_cell = None
fit_dims = None
pack_specs = {}

for _, cell in candidate_cells.iterrows():
    cell_wh = cell['Nominal Voltage (V)'] * cell['Cell Capacity (Ah)'] / 1000  # in kWh
    parallel = int(np.ceil(energy_required_kwh / cell_wh))
    series = int(np.ceil(expected_voltage / cell['Nominal Voltage (V)']))
    total_cells = series * parallel

    fit = can_fit(cell, series, parallel)
    if fit:
        best_cell = cell
        fit_dims = fit
        break

if best_cell is not None:
    st.success(f"Selected Cell: {best_cell['Cell Name']} ({best_cell['Chemistry']})")

    pack_specs = {
        "Required Energy (kWh)": round(energy_required_kwh, 2),
        "Cell Voltage (V)": best_cell['Nominal Voltage (V)'],
        "Cell Capacity (Ah)": best_cell['Capacity (Ah)'],
        "Series (#)": series,
        "Parallel (#)": parallel,
        "Total Cells": total_cells,
        "Pack Capacity (Ah)": round(parallel * best_cell['Capacity (Ah)'], 2),
        "Pack Voltage (V)": round(series * best_cell['Nominal Voltage (V)'], 2),
        "Pack Volume (mm)": f"{int(fit_dims[0])} x {int(fit_dims[1])} x {int(fit_dims[2])}",
        "Pack Energy Density (Wh/kg)": round(best_cell['Wh/kg (pack) (cells + 30%)'], 2),
        "Cycle Life": int(best_cell['Cycle life at 1C'])
    }

    st.subheader("Battery Pack Specifications")
    for k, v in pack_specs.items():
        st.write(f"**{k}:** {v}")
else:
    st.error("No suitable cell found that fits within the available space. Try different dimensions or lower energy requirements.")

# =====================
# Raw Data Option
# =====================
with st.expander("See Available Cells Considered"):
    st.dataframe(candidate_cells[['Cell Name', 'Chemistry', 'Nominal Voltage (V)', 'Capacity (Ah)', 'Cycle life at 1C', 'Wh/kg (pack) (cells + 30%)']])
