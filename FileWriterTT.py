from TimeTagger import createTimeTagger, FileWriter
import time

# Initialize the Time Tagger
tagger = createTimeTagger()  # Use virtual=True for simulation mode

# Configure channels (example: detector on channel 1, laser sync on channel 2)
channels = [1, 2]  # List of channels to record

# Define output file path
output_file = "time_tags.ttbin"  # Binary format (default for Time Tagger)

# Create FileWriter instance
file_writer = FileWriter(tagger, filename=output_file, channels=channels)

# Start recording
file_writer.start()
print(f"Recording started. Saving data to: {output_file}")

# Record for a specified duration (e.g., 10 seconds)
recording_time = 10  # seconds
time.sleep(recording_time)

# Stop recording and close the file
file_writer.stop()
print("Recording stopped.")
