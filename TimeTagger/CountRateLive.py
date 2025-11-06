import TimeTagger
import sys
from pathlib import Path
from qtpy.QtWidgets import QApplication

# Add parent directory to path to import plot_widgets
parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))

from plot_widgets.live_plot_napari_widget import live_plot

# Initialize TimeTagger
tagger = TimeTagger.createTimeTagger()
# Set bin width 
binwidth = int(5e9)
n_values = 1
counter = TimeTagger.Counter(tagger, [1], binwidth, n_values)

def get_count_with_overflow():
    data = counter.getData()
    count_rate = data[0][0]/(binwidth/1e12)
    #count_rate = counter.getDataNormalized()
    # Check if any bins are in overflow mode
    counter_data = counter.getDataObject()
    overflow = counter_data.overflow  # Access as attribute, not as a method
    return count_rate, overflow

# Create Qt application if not already running
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

# Create live plot widget
widget = live_plot(
    measure_function=get_count_with_overflow,
    histogram_range=100,  # Show last 100 points
    dt=0.1  # Update every 200ms
)

widget.show()
app.exec_()

# Clean up
TimeTagger.freeTimeTagger(tagger)