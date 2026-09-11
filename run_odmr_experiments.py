"""
ODMR experiment runner — edit parameters here, then run:

    python run_odmr_experiments.py

Uncomment the experiment block you want. Instrument IPs live in common/utils.py.
Experiment logic lives in PulseBlaster/odmr_experiments.py (ODMRExperiments).
"""

import numpy as np

from PulseBlaster.swabian_pulse_streamer import SwabianPulseController
from PulseBlaster.rigol_dsg836 import RigolDSG836Controller
from PulseBlaster.odmr_experiments import ODMRExperiments


def main():
    print("🚀 Starting ODMR experiments...")

    controller = SwabianPulseController()
    if not controller.is_connected:
        print("❌ Pulse controller not connected.")
        return

    try:
        rigol = RigolDSG836Controller()
        if rigol.connect():
            print("✅ RIGOL DSG836 connected")
        else:
            print("⚠️  RIGOL not connected — continuing without MW control")
            rigol = None
    except Exception as e:
        print(f"⚠️  RIGOL connection failed: {e} — continuing without MW control")
        rigol = None

    experiments = ODMRExperiments(controller, rigol)

    try:
        # ------------------------------------------------------------------
        # 1. CW ODMR contrast
        # ------------------------------------------------------------------
        # print("\n" + "=" * 50)
        # frequencies = np.linspace(2.8e9, 2.95e9, 50)
        # experiments.odmr_contrast(
        #     mw_frequencies=frequencies,
        #     laser_duration=100000,
        #     mw_duration=100000,
        #     detection_duration=100000,
        #     laser_delay=0,
        #     mw_delay=0,
        #     detection_delay=1500,
        #     sequence_interval=2000,
        #     repetitions=5000,
        #     plot_sequence=False,
        #     live_plot=True,
        # )
        # experiments.plot_results('odmr_contrast')

        # ------------------------------------------------------------------
        # 2. Readout transient (calibrate detection_delay / detection_duration)
        # ------------------------------------------------------------------
        # print("\n" + "=" * 50)
        # experiments.readout_transient(
        #     mw_frequency=2.846e9,
        #     mw_duration=1000,
        #     init_laser_duration=3000,
        #     readout_laser_duration=3000,
        #     init_laser_delay=0,
        #     mw_gap=500,
        #     readout_gap=500,
        #     pre_readout=200,
        #     sequence_interval=2000,
        #     repetitions=200000,
        #     binwidth_ns=4,
        #     plot_sequence=False,
        # )
        # experiments.plot_results('readout_transient')

        # ------------------------------------------------------------------
        # 3. Pulsed ODMR contrast
        # ------------------------------------------------------------------
        # print("\n" + "=" * 50)
        # frequencies = np.linspace(2.8e9, 2.95e9, 80)
        # experiments.pulsed_odmr_contrast(
        #     mw_frequencies=frequencies,
        #     mw_duration=1000,
        #     init_laser_duration=3000,
        #     readout_laser_duration=1000,
        #     detection_duration=300,
        #     init_laser_delay=0,
        #     mw_gap=500,
        #     readout_gap=500,
        #     detection_delay=100,
        #     sequence_interval=2000,
        #     repetitions=400000,
        #     plot_sequence=False,
        #     live_plot=True,
        # )
        # experiments.plot_results('pulsed_odmr_contrast')

        # ------------------------------------------------------------------
        # 4. Rabi oscillation contrast  ← active
        # ------------------------------------------------------------------
        print("\n" + "=" * 50)
        mw_durations = np.linspace(0, 1008, 128)
        experiments.rabi_oscillation_contrast(
            mw_durations=mw_durations,
            mw_frequency=2.846e9,
            init_laser_duration=3000,
            readout_laser_duration=1000,
            detection_duration=300,
            init_laser_delay=0,
            mw_gap=500,
            readout_gap=500,
            detection_delay=100,
            sequence_interval=2000,
            repetitions=400000,
            plot_sequence=False,
            live_plot=True,
        )
        experiments.plot_results('rabi_contrast')

        # ------------------------------------------------------------------
        # 5. T1 decay contrast
        # ------------------------------------------------------------------
        # print("\n" + "=" * 50)
        # delay_times = np.linspace(0, 30e6, 50)
        # # delay_times = np.logspace(np.log10(0.5e3), np.log10(5e6), 50)
        # experiments.t1_decay_contrast(
        #     delay_times=delay_times,
        #     init_laser_duration=50000,
        #     readout_laser_duration=50000,
        #     detection_duration=3000,
        #     init_laser_delay=0,
        #     detection_delay=1500,
        #     sequence_interval=2000,
        #     repetitions=3000,
        #     plot_sequence=False,
        #     live_plot=True,
        # )
        # experiments.plot_results('t1_contrast')

        print("\n✅ Experiment completed!")

    except Exception as e:
        print(f"❌ Error during experiments: {e}")
        raise

    finally:
        if rigol:
            try:
                rigol.set_rf_output(False)
            except Exception:
                pass
            rigol.disconnect()
        controller.disconnect()


if __name__ == "__main__":
    main()
