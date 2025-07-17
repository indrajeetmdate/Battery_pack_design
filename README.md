🔧 Inputs (user-provided):
Application Type: EV / Stationary Storage

Expected Voltage (V)

Km Expected (for EV) or Backup Hours (for stationary)

Total Load (kW) (only for stationary)

Cell Type (optional) — suggest one if not provided

Available Space (mm): length, breadth, height



📤 Outputs:
Suggested Cell Name

Pack Voltage (V)

Cells in Series / Parallel

Pack Capacity (Ah), Energy (kWh)

Pack Weight & Volume

Volume Fit Status — does it fit in available space?

Pack Dimensions (Length × Breadth × Height in mm)



📦 Space Optimization Logic:
Prismatic:

      Length = Cell length × Series
      
      Breadth = Cell breadth
      
      Height = Cell height × Parallel

Cylindrical:

      Length = Diameter × Series
      
      Breadth = (Diameter × ceil(Parallel / Rows))
      
      Height = Cell height

Volume is verified as: Length × Breadth × Height ≤ Available Volume.
