"""
ODMR GUI Application
--------------------
Graphical user interface for controlling continuous wave ODMR experiments.
Provides easy parameter control and real-time result visualization.

Author: NV Lab
Date: 2025
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import threading
import time
import json
from typing import Dict, List
import os

# Import the ODMR experiment classes
from swabian_pulse_streamer import SwabianPulseController
from rigol_dsg836 import RigolDSG836Controller
from odmr_experiments import ODMRExperiments


class ODMRGuiApp:
    """
    GUI Application for ODMR experiments with parameter control and visualization.
    """
    
    def __init__(self, root):
        """Initialize the ODMR GUI application."""
        self.root = root
        self.root.title("ODMR Control Center")
        self.root.geometry("1200x800")
        
        # Initialize controllers and experiments
        self.pulse_controller = None
        self.mw_generator = None
        self.experiments = None
        self.is_running = False
        self.current_results = None
        
        # Create the GUI layout
        self.create_widgets()
        self.setup_plot()
        
        # Try to connect to devices on startup
        self.connect_devices()
    
    def create_widgets(self):
        """Create and arrange all GUI widgets."""
        # Main container with tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Control tab
        self.control_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.control_frame, text="ODMR Control")
        
        # Settings tab
        self.settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_frame, text="Device Settings")
        
        # Create control widgets
        self.create_control_widgets()
        
        # Create settings widgets
        self.create_settings_widgets()
    
    def create_control_widgets(self):
        """Create the main control interface."""
        # Left panel for parameters
        left_panel = ttk.Frame(self.control_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        
        # Right panel for plot
        right_panel = ttk.Frame(self.control_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Parameter input section
        params_frame = ttk.LabelFrame(left_panel, text="ODMR Parameters", padding=10)
        params_frame.pack(fill=tk.X, pady=5)
        
        # Frequency settings
        freq_frame = ttk.LabelFrame(params_frame, text="Frequency Range", padding=5)
        freq_frame.pack(fill=tk.X, pady=5)
        
        self.create_parameter_input(freq_frame, "Start Freq (GHz):", "start_freq", "2.80", 0)
        self.create_parameter_input(freq_frame, "Stop Freq (GHz):", "stop_freq", "2.90", 1)
        self.create_parameter_input(freq_frame, "Num Points:", "num_points", "51", 2)
        
        # Timing parameters
        timing_frame = ttk.LabelFrame(params_frame, text="Timing Parameters (ns)", padding=5)
        timing_frame.pack(fill=tk.X, pady=5)
        
        self.create_parameter_input(timing_frame, "Laser Duration:", "laser_duration", "2000", 0)
        self.create_parameter_input(timing_frame, "MW Duration:", "mw_duration", "2000", 1)
        self.create_parameter_input(timing_frame, "Detection Duration:", "detection_duration", "1000", 2)
        
        # Delay parameters
        delay_frame = ttk.LabelFrame(params_frame, text="Delay Parameters (ns)", padding=5)
        delay_frame.pack(fill=tk.X, pady=5)
        
        self.create_parameter_input(delay_frame, "Laser Delay:", "laser_delay", "0", 0)
        self.create_parameter_input(delay_frame, "MW Delay:", "mw_delay", "0", 1)
        self.create_parameter_input(delay_frame, "Detection Delay:", "detection_delay", "0", 2)
        
        # Sequence parameters
        seq_frame = ttk.LabelFrame(params_frame, text="Sequence Parameters", padding=5)
        seq_frame.pack(fill=tk.X, pady=5)
        
        self.create_parameter_input(seq_frame, "Sequence Interval (ns):", "sequence_interval", "10000", 0)
        self.create_parameter_input(seq_frame, "Repetitions:", "repetitions", "100", 1)
        
        # Control buttons
        button_frame = ttk.Frame(left_panel)
        button_frame.pack(fill=tk.X, pady=10)
        
        self.start_button = ttk.Button(button_frame, text="Start ODMR", command=self.start_odmr)
        self.start_button.pack(fill=tk.X, pady=2)
        
        self.stop_button = ttk.Button(button_frame, text="Stop", command=self.stop_odmr, state=tk.DISABLED)
        self.stop_button.pack(fill=tk.X, pady=2)
        
        # Status and file operations
        status_frame = ttk.LabelFrame(left_panel, text="Status & Files", padding=5)
        status_frame.pack(fill=tk.X, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.pack(anchor=tk.W)
        
        ttk.Button(status_frame, text="Save Parameters", command=self.save_parameters).pack(fill=tk.X, pady=1)
        ttk.Button(status_frame, text="Load Parameters", command=self.load_parameters).pack(fill=tk.X, pady=1)
        ttk.Button(status_frame, text="Save Results", command=self.save_results).pack(fill=tk.X, pady=1)
        
        # Progress bar
        self.progress = ttk.Progressbar(left_panel, mode='determinate')
        self.progress.pack(fill=tk.X, pady=5)
        
        # Plot area (will be filled by setup_plot)
        self.plot_frame = right_panel
    
    def create_settings_widgets(self):
        """Create device settings interface."""
        # Connection settings
        conn_frame = ttk.LabelFrame(self.settings_frame, text="Device Connections", padding=10)
        conn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Pulse Streamer settings
        ps_frame = ttk.Frame(conn_frame)
        ps_frame.pack(fill=tk.X, pady=5)
        ttk.Label(ps_frame, text="Pulse Streamer:").pack(side=tk.LEFT)
        self.ps_status = ttk.Label(ps_frame, text="Disconnected", foreground="red")
        self.ps_status.pack(side=tk.LEFT, padx=10)
        ttk.Button(ps_frame, text="Connect", command=self.connect_pulse_streamer).pack(side=tk.RIGHT)
        
        # RIGOL settings
        rigol_frame = ttk.Frame(conn_frame)
        rigol_frame.pack(fill=tk.X, pady=5)
        ttk.Label(rigol_frame, text="RIGOL DSG836:").pack(side=tk.LEFT)
        self.rigol_ip = tk.StringVar(value="192.168.0.222")
        ttk.Entry(rigol_frame, textvariable=self.rigol_ip, width=15).pack(side=tk.LEFT, padx=5)
        self.rigol_status = ttk.Label(rigol_frame, text="Disconnected", foreground="red")
        self.rigol_status.pack(side=tk.LEFT, padx=10)
        ttk.Button(rigol_frame, text="Connect", command=self.connect_rigol).pack(side=tk.RIGHT)
        
        # MW power setting
        power_frame = ttk.Frame(conn_frame)
        power_frame.pack(fill=tk.X, pady=5)
        ttk.Label(power_frame, text="MW Power (dBm):").pack(side=tk.LEFT)
        self.mw_power = tk.StringVar(value="-10.0")
        ttk.Entry(power_frame, textvariable=self.mw_power, width=10).pack(side=tk.LEFT, padx=5)
    
    def create_parameter_input(self, parent, label_text, var_name, default_value, row):
        """Create a parameter input field."""
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=2)
        parent.columnconfigure(0, weight=1)
        
        ttk.Label(frame, text=label_text).pack(side=tk.LEFT)
        
        var = tk.StringVar(value=default_value)
        setattr(self, var_name, var)
        
        entry = ttk.Entry(frame, textvariable=var, width=12)
        entry.pack(side=tk.RIGHT)
    
    def setup_plot(self):
        """Setup the matplotlib plot for displaying results."""
        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        
        self.canvas = FigureCanvasTkAgg(self.fig, self.plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Initial empty plot
        self.ax.set_xlabel('Frequency (GHz)')
        self.ax.set_ylabel('Count Rate (Hz)')
        self.ax.set_title('ODMR Spectrum')
        self.ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()
    
    def connect_devices(self):
        """Try to connect to devices on startup."""
        self.connect_pulse_streamer()
        self.connect_rigol()
    
    def connect_pulse_streamer(self):
        """Connect to Swabian Pulse Streamer."""
        try:
            self.pulse_controller = SwabianPulseController()
            if self.pulse_controller.is_connected:
                self.ps_status.config(text="Connected", foreground="green")
                self.update_status("Pulse Streamer connected")
            else:
                self.ps_status.config(text="Failed", foreground="red")
                self.update_status("Pulse Streamer connection failed")
        except Exception as e:
            self.ps_status.config(text="Error", foreground="red")
            self.update_status(f"Pulse Streamer error: {e}")
    
    def connect_rigol(self):
        """Connect to RIGOL DSG836."""
        try:
            ip = self.rigol_ip.get()
            self.mw_generator = RigolDSG836Controller(ip)
            if self.mw_generator.connect():
                self.rigol_status.config(text="Connected", foreground="green")
                self.update_status(f"RIGOL connected at {ip}")
            else:
                self.rigol_status.config(text="Failed", foreground="red")
                self.update_status(f"RIGOL connection failed at {ip}")
                self.mw_generator = None
        except Exception as e:
            self.rigol_status.config(text="Error", foreground="red")
            self.update_status(f"RIGOL error: {e}")
            self.mw_generator = None
    
    def update_status(self, message):
        """Update the status label."""
        self.status_label.config(text=message)
        self.root.update_idletasks()
    
    def get_parameters(self) -> Dict:
        """Get all parameters from the GUI."""
        try:
            # Generate frequency list
            start_freq = float(self.start_freq.get()) * 1e9  # Convert GHz to Hz
            stop_freq = float(self.stop_freq.get()) * 1e9   # Convert GHz to Hz
            num_points = int(self.num_points.get())
            frequencies = np.linspace(start_freq, stop_freq, num_points)
            
            params = {
                'mw_frequencies': frequencies.tolist(),
                'laser_duration': int(self.laser_duration.get()),
                'mw_duration': int(self.mw_duration.get()),
                'detection_duration': int(self.detection_duration.get()),
                'laser_delay': int(self.laser_delay.get()),
                'mw_delay': int(self.mw_delay.get()),
                'detection_delay': int(self.detection_delay.get()),
                'sequence_interval': int(self.sequence_interval.get()),
                'repetitions': int(self.repetitions.get())
            }
            return params
        except ValueError as e:
            messagebox.showerror("Parameter Error", f"Invalid parameter value: {e}")
            return None
    
    def start_odmr(self):
        """Start the ODMR measurement in a separate thread."""
        if self.is_running:
            return
        
        # Check device connections
        if not self.pulse_controller or not self.pulse_controller.is_connected:
            messagebox.showerror("Connection Error", "Pulse Streamer not connected!")
            return
        
        # Get parameters
        params = self.get_parameters()
        if params is None:
            return
        
        # Initialize experiments
        if not self.experiments:
            self.experiments = ODMRExperiments(self.pulse_controller, self.mw_generator)
        
        # Update UI state
        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.progress['value'] = 0
        
        # Start measurement in separate thread
        self.measurement_thread = threading.Thread(target=self.run_odmr_measurement, args=(params,))
        self.measurement_thread.daemon = True
        self.measurement_thread.start()
    
    def run_odmr_measurement(self, params):
        """Run the ODMR measurement (called in separate thread)."""
        try:
            self.update_status("Starting ODMR measurement...")
            
            frequencies = params['mw_frequencies']
            total_points = len(frequencies)
            
            # Set MW power if RIGOL is connected
            if self.mw_generator:
                power = float(self.mw_power.get())
                self.mw_generator.set_power(power)
            
            # Run the measurement with progress updates
            self.current_results = {'frequencies': [], 'count_rates': []}
            
            for i, freq in enumerate(frequencies):
                if not self.is_running:  # Check for stop signal
                    break
                
                # Update progress
                progress = (i / total_points) * 100
                self.progress['value'] = progress
                self.update_status(f"Measuring point {i+1}/{total_points}: {freq/1e9:.4f} GHz")
                
                # Run single frequency measurement
                single_freq_params = params.copy()
                single_freq_params['mw_frequencies'] = [freq]
                
                result = self.experiments.continuous_wave_odmr(**single_freq_params)
                
                if result and 'count_rates' in result and len(result['count_rates']) > 0:
                    self.current_results['frequencies'].append(freq)
                    self.current_results['count_rates'].append(result['count_rates'][0])
                    
                    # Update plot in real-time
                    self.root.after(0, self.update_plot)
            
            if self.is_running:  # Only if not stopped by user
                self.progress['value'] = 100
                self.update_status("ODMR measurement completed!")
            
        except Exception as e:
            self.update_status(f"Error during measurement: {e}")
            messagebox.showerror("Measurement Error", f"Error during ODMR measurement:\n{e}")
        
        finally:
            # Reset UI state
            self.root.after(0, self.measurement_finished)
    
    def measurement_finished(self):
        """Called when measurement is finished or stopped."""
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
    
    def stop_odmr(self):
        """Stop the current ODMR measurement."""
        self.is_running = False
        self.update_status("Stopping measurement...")
        
        # Stop the pulse sequence if running
        if self.pulse_controller:
            try:
                self.pulse_controller.stop_sequence()
            except:
                pass
        
        # Turn off MW output
        if self.mw_generator:
            try:
                self.mw_generator.set_rf_output(False)
            except:
                pass
    
    def update_plot(self):
        """Update the plot with current results."""
        if not self.current_results or len(self.current_results['frequencies']) == 0:
            return
        
        self.ax.clear()
        
        frequencies = np.array(self.current_results['frequencies']) / 1e9  # Convert to GHz
        count_rates = self.current_results['count_rates']
        
        self.ax.plot(frequencies, count_rates, 'bo-', markersize=4, linewidth=1)
        self.ax.set_xlabel('Frequency (GHz)')
        self.ax.set_ylabel('Count Rate (Hz)')
        self.ax.set_title('ODMR Spectrum (Live)')
        self.ax.grid(True, alpha=0.3)
        
        # Auto-scale with some padding
        if len(frequencies) > 1:
            freq_range = frequencies.max() - frequencies.min()
            self.ax.set_xlim(frequencies.min() - 0.05*freq_range, 
                           frequencies.max() + 0.05*freq_range)
        
        if len(count_rates) > 1:
            count_range = max(count_rates) - min(count_rates)
            if count_range > 0:
                self.ax.set_ylim(min(count_rates) - 0.1*count_range, 
                               max(count_rates) + 0.1*count_range)
        
        self.fig.tight_layout()
        self.canvas.draw()
    
    def save_parameters(self):
        """Save current parameters to a JSON file."""
        try:
            params = self.get_parameters()
            if params is None:
                return
            
            # Convert frequencies back to GHz for saving
            params['start_freq_ghz'] = float(self.start_freq.get())
            params['stop_freq_ghz'] = float(self.stop_freq.get())
            params['num_points'] = int(self.num_points.get())
            params['mw_power_dbm'] = float(self.mw_power.get())
            
            # Remove the frequency list for cleaner save file
            del params['mw_frequencies']
            
            filename = filedialog.asksaveasfilename(
                title="Save Parameters",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            
            if filename:
                with open(filename, 'w') as f:
                    json.dump(params, f, indent=2)
                self.update_status(f"Parameters saved to {filename}")
        
        except Exception as e:
            messagebox.showerror("Save Error", f"Error saving parameters: {e}")
    
    def load_parameters(self):
        """Load parameters from a JSON file."""
        try:
            filename = filedialog.askopenfilename(
                title="Load Parameters",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            
            if filename:
                with open(filename, 'r') as f:
                    params = json.load(f)
                
                # Set frequency parameters
                if 'start_freq_ghz' in params:
                    self.start_freq.set(str(params['start_freq_ghz']))
                if 'stop_freq_ghz' in params:
                    self.stop_freq.set(str(params['stop_freq_ghz']))
                if 'num_points' in params:
                    self.num_points.set(str(params['num_points']))
                
                # Set timing parameters
                for param in ['laser_duration', 'mw_duration', 'detection_duration',
                             'laser_delay', 'mw_delay', 'detection_delay',
                             'sequence_interval', 'repetitions']:
                    if param in params:
                        getattr(self, param).set(str(params[param]))
                
                # Set MW power
                if 'mw_power_dbm' in params:
                    self.mw_power.set(str(params['mw_power_dbm']))
                
                self.update_status(f"Parameters loaded from {filename}")
        
        except Exception as e:
            messagebox.showerror("Load Error", f"Error loading parameters: {e}")
    
    def save_results(self):
        """Save current results to a file."""
        if not self.current_results or len(self.current_results['frequencies']) == 0:
            messagebox.showwarning("No Data", "No results to save!")
            return
        
        try:
            filename = filedialog.asksaveasfilename(
                title="Save Results",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("CSV files", "*.csv"), ("All files", "*.*")]
            )
            
            if filename:
                if filename.endswith('.csv'):
                    # Save as CSV
                    import csv
                    with open(filename, 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(['Frequency_GHz', 'Count_Rate_Hz'])
                        for freq, count in zip(self.current_results['frequencies'], 
                                             self.current_results['count_rates']):
                            writer.writerow([freq/1e9, count])
                else:
                    # Save as JSON
                    data = {
                        'frequencies_hz': self.current_results['frequencies'],
                        'count_rates_hz': self.current_results['count_rates'],
                        'parameters': self.get_parameters(),
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    with open(filename, 'w') as f:
                        json.dump(data, f, indent=2)
                
                self.update_status(f"Results saved to {filename}")
        
        except Exception as e:
            messagebox.showerror("Save Error", f"Error saving results: {e}")
    
    def on_closing(self):
        """Handle application closing."""
        if self.is_running:
            if messagebox.askokcancel("Quit", "Measurement in progress. Stop and quit?"):
                self.stop_odmr()
            else:
                return
        
        # Clean up connections
        if self.experiments:
            try:
                self.experiments.cleanup()
            except:
                pass
        
        if self.mw_generator:
            try:
                self.mw_generator.set_rf_output(False)
                self.mw_generator.disconnect()
            except:
                pass
        
        if self.pulse_controller:
            try:
                self.pulse_controller.disconnect()
            except:
                pass
        
        self.root.destroy()


def main():
    """Main function to run the ODMR GUI application."""
    root = tk.Tk()
    app = ODMRGuiApp(root)
    
    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Start the GUI event loop
    root.mainloop()


if __name__ == "__main__":
    main() 