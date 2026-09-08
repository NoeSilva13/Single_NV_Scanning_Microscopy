"""
Entry point for ODMR-family experiments (CW ODMR, pulsed ODMR, Rabi, T1, readout transient).

Edit parameters inside PulseBlaster/odmr_experiments.py :: run_example_experiments(),
then run from the repository root:

    python run_odmr_experiments.py
"""

from PulseBlaster.odmr_experiments import run_example_experiments


if __name__ == "__main__":
    run_example_experiments()
