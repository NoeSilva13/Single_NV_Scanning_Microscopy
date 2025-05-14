from TimeTagger import createTimeTagger, Countrate
import time

class TimeTagController:
    """
    Controller for Swabian TimeTagger device.
    Handles initialization and photon counting functionality.
    """
    def __init__(self):
        """
        Initialize the TimeTagger device and set up the counter.
        """
        try:
            self.tagger = createTimeTagger()
            if not self.tagger:
                raise RuntimeError("TimeTagger device not found!")
            self.tagger.reset()  # Reset to default state
            
            # Initialize TimeTagger counter for SPD
            self.spd_counter_tt = Countrate(self.tagger, channels=[1])
            
        except Exception as e:
            raise RuntimeError(f"Failed to initialize TimeTagger: {str(e)}")

    def read_spd_count_tt(self, sampling_time=0.1):
        """
        Read photon counts from SPD using Swabian TimeTagger.

        Args:
            sampling_time (float): Time to count photons in seconds
        
        Returns:
            int: Number of counts during sampling period
        """
        # Clear and measure counts
        self.spd_counter_tt.clear()
        time.sleep(sampling_time)
        counts = self.spd_counter_tt.getData()[0]  # Extract counts from channel 1

        return int(counts)  # Return count during sampling period

    def close(self):
        """
        Clean up TimeTagger resources.
        """
        if hasattr(self, 'tagger'):
            self.tagger.close()
