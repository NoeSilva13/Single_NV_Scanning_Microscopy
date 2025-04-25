import pyvisa

# Initialize communication
rm = pyvisa.ResourceManager()

print(rm.list_resources())

pm400 = rm.open_resource('USB0::0x1313::0x8075::P5006633::INSTR')  # Replace with your device ID

# Query identification (optional)
print(pm400.query('*IDN?'))  # Should return PM400 model info

# Read optical power in Watts
power = float(pm400.query('MEAS:POW?'))
print(f"Optical Power: {power * 1e3:.3f} mW")  # Convert to mW

pm400.close()