import streamlit as st
import pandas as pd
import math

# Load cell data
@st.cache_data
def load_data():
    return pd.read_excel("Pack_calculations.xlsx")

df = load_data()

# --- UI ---
st.title("Custom Battery Pack Design Calculator")

# Application type
app_type = st.radio("Application Type", ["EV", "Stationary Storage"])
exp_voltage = st.number_input("Expected Voltage (V)", min_value=12, max_value=1000, step=1)

if app_type == "EV":
    km_expected = st.number_input("Km Expected", min_value=1)
else:
    backup_hours = st.number_input("Hours of Backup Required", min_value=1.0, step=0.5)
    total_load_kw = st.number_input("Total Load (kW)", min_value=0.1, step=0.1)

cell_choice = st.selectbox("Choose Cell Type (optional)", ["Suggest for me"] + df["Cell Name"].tolist())

st.subheader("Available Space (in mm)")
avail_len = st.number_input("Available Length (mm)", min_value=100)
avail_brd = st.number_input("Available Breadth (mm)", min_value=100)
avail_hei = st.number_input("Available Height (mm)", min_value=100)

if st.button("Calculate Pack Design"):
    # Energy required
    energy_required = 0
    if app_type == "EV":
        energy_required = (km_expected / 100) * 3.3  # Assuming 3.3 kWh/100km
    else:
        energy_required = backup_hours * total_load_kw

    result = None
    for i, row in df.iterrows():
        cell_voltage = row["Nominal Voltage (V)"]
        cell_capacity = row["Cell Capacity (Ah)"]
        cell_energy = cell_voltage * cell_capacity
        series = math.ceil(exp_voltage / cell_voltage)
        parallel = math.ceil((energy_required * 1000) / (cell_energy * series))
        total_cells = series * parallel

        pack_energy_kwh = (cell_energy * series * parallel) / 1000
        pack_weight = row["Cell Weight (kg)"] * total_cells * 1.3

        # Get dimensions
        if row["Shape"].lower() == "prismatic":
            pack_len = row["Cell Diameter/Cell Length (mm)"] * series
            pack_brd = row["Third dimension (mm)"]
            pack_hei = row["Cell height (mm)"] * parallel
        else:
            diameter = row["Cell Diameter/Cell Length (mm)"]
            pack_len = diameter * series
            rows = math.ceil(math.sqrt(parallel))
            cols = math.ceil(parallel / rows)
            pack_brd = diameter * cols
            pack_hei = row["Cell height (mm)"]

        volume_ok = (pack_len <= avail_len) and (pack_brd <= avail_brd) and (pack_hei <= avail_hei)

        if volume_ok and (cell_choice == "Suggest for me" or cell_choice == row["Cell Name"]):
            result = {
                "Cell Name": row["Cell Name"],
                "Shape": row["Shape"],
                "Series": series,
                "Parallel": parallel,
                "Pack Voltage (V)": round(series * cell_voltage, 2),
                "Pack Capacity (Ah)": round(parallel * cell_capacity, 2),
                "Total Energy (kWh)": round(pack_energy_kwh, 2),
                "Pack Weight (kg)": round(pack_weight, 2),
                "Pack Dimensions (mm)": f"{int(pack_len)} x {int(pack_brd)} x {int(pack_hei)}",
                "Fits in Space?": "✅ Yes"
            }
            break

    if result:
        st.success("Pack Design Successful")
        for k, v in result.items():
            st.write(f"**{k}**: {v}")
    else:
        st.error("No suitable cell found that fits within the available space.")
