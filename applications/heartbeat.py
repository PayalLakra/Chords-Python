# import sys
# import numpy as np
# import time
# from pylsl import StreamInlet, resolve_stream
# from scipy.signal import butter, lfilter, iirnotch, find_peaks
# import pyqtgraph as pg  # For real-time plotting
# from pyqtgraph.Qt import QtWidgets, QtCore  # PyQt components for GUI
# import signal  # For handling Ctrl+C
# from collections import deque  # For creating a ring buffer

# # Initialize global variables
# inlet = None
# data_buffer = np.zeros(2000)  # Buffer to hold the last 2000 samples for ECG data

# # Function to design a Butterworth filter
# def butter_filter(cutoff, fs, order=4, btype='low'):
#     nyquist = 0.5 * fs  # Nyquist frequency
#     normal_cutoff = cutoff / nyquist
#     b, a = butter(order, normal_cutoff, btype=btype, analog=False)
#     return b, a

# # Apply the Butterworth filter to the data
# def apply_filter(data, b, a):
#     return lfilter(b, a, data)

# # Notch filter for powerline interference removal
# def notch_filter(data, fs, freq=50.0, quality=30):
#     nyquist = 0.5 * fs
#     normal_cutoff = freq / nyquist
#     b, a = iirnotch(normal_cutoff, quality)
#     return lfilter(b, a, data)

# # Function to detect heartbeats using peak detection
# def detect_heartbeats(ecg_data, sampling_rate):
#     peaks, _ = find_peaks(ecg_data, distance=sampling_rate * 0.6, prominence=0.5)  # Adjust as necessary
#     return peaks

# class DataCollector(QtCore.QThread):
#     data_ready = QtCore.pyqtSignal(np.ndarray)

#     def __init__(self):
#         super().__init__()
#         self.running = True
#         self.sampling_rate = None

#     def run(self):
#         global inlet
#         print("Looking for LSL stream...")
#         streams = resolve_stream('name', 'BioAmpDataStream')
        
#         if not streams:
#             print("No LSL Stream found! Exiting...")
#             sys.exit(0)

#         inlet = StreamInlet(streams[0])
#         self.sampling_rate = inlet.info().nominal_srate()
#         print(f"Detected sampling rate: {self.sampling_rate} Hz")

#         # Create filters
#         low_cutoff = 40.0  # 40 Hz low-pass filter
#         high_cutoff = 0.5  # 0.5 Hz high-pass filter
#         notch_freq = 50.0  # Powerline interference at 50 Hz

#         # Design the filters
#         self.low_b, self.low_a = butter_filter(low_cutoff, self.sampling_rate, order=4, btype='low')
#         self.high_b, self.high_a = butter_filter(high_cutoff, self.sampling_rate, order=4, btype='high')
#         self.notch_b, self.notch_a = iirnotch(notch_freq / (0.5 * self.sampling_rate), 30)

#         while self.running:
#             # Pull multiple samples at once
#             samples, _ = inlet.pull_chunk(timeout=0.0, max_samples=10)  # Pull up to 10 samples
#             if samples:
#                 # Update data buffer
#                 global data_buffer
#                 data_buffer = np.roll(data_buffer, -len(samples))  # Shift data left
#                 data_buffer[-len(samples):] = [sample[0] for sample in samples]  # Add new samples to the end

#                 # Apply filters to the signal
#                 filtered_data = apply_filter(data_buffer, self.high_b, self.high_a)  # High-pass
#                 filtered_data = apply_filter(filtered_data, self.low_b, self.low_a)   # Low-pass
#                 filtered_data = apply_filter(filtered_data, self.notch_b, self.notch_a)  # Notch filter

#                 self.data_ready.emit(filtered_data)  # Emit the filtered data for plotting

#             time.sleep(0.01)

#     def stop(self):
#         self.running = False

# class ECGApp(QtWidgets.QMainWindow):
#     def __init__(self):
#         super().__init__()

#         # Create a plot widget
#         self.plot_widget = pg.PlotWidget(title="ECG Signal")
#         self.setCentralWidget(self.plot_widget)

#         # Set background to white
#         self.plot_widget.setBackground('w')

#         # Create a label to display heart rate
#         self.heart_rate_label = QtWidgets.QLabel("Heart rate: - bpm", self)
#         self.heart_rate_label.setStyleSheet("font-size: 20px; font-weight: bold;")
#         self.heart_rate_label.setAlignment(QtCore.Qt.AlignCenter)

#         # Layout
#         layout = QtWidgets.QVBoxLayout()
#         layout.addWidget(self.plot_widget)
#         layout.addWidget(self.heart_rate_label)

#         container = QtWidgets.QWidget()
#         container.setLayout(layout)
#         self.setCentralWidget(container)

#         self.ecg_buffer = []    # Buffer to hold the ECG data
#         self.r_peak_times = deque(maxlen=10)  # Ring buffer for R-peak timestamps

#         # Data collector thread
#         self.data_collector = DataCollector()
#         self.data_collector.data_ready.connect(self.update_plot)
#         self.data_collector.start()

#         # Store the x-axis time window
#         self.time_axis = np.linspace(0, 2000/500, 2000)  

#         # Set fixed y-axis limits
#         self.plot_widget.setYRange(-8000,8000)  # Adjust the range based on your ECG signal characteristics

#     def update_plot(self, ecg_data):
#         self.ecg_buffer = ecg_data  # Update buffer
#         self.plot_widget.clear()
#         # Set a fixed window (time axis) to ensure stable plotting
#         self.plot_widget.plot(self.time_axis, self.ecg_buffer, pen='#ffa500')  # Plot ECG data with orange line
#         self.plot_widget.setXRange(self.time_axis[0], self.time_axis[-1], padding=0)

#         # Detect heartbeats in real time
#         heartbeats = detect_heartbeats(np.array(self.ecg_buffer), self.data_collector.sampling_rate)

#         # Calculate R-peak times using sample indices and the sampling rate
#         if len(heartbeats) > 0:
#             current_peak_times = [(peak / self.data_collector.sampling_rate) for peak in heartbeats]
#             for peak_time in current_peak_times:
#                 self.r_peak_times.append(time.time())  # Store the real-world timestamp of the R-peak

#         self.calculate_heart_rate()   # Calculate heart rate after detecting R-peaks

#     def calculate_heart_rate(self):
#         if len(self.r_peak_times) > 1:
#             # Calculate the time intervals between successive R-peaks
#             intervals = np.diff(self.r_peak_times)
            
#             # Filter intervals that are positive and non-zero to avoid issues
#             valid_intervals = intervals[intervals > 0]
            
#             if len(valid_intervals) > 0:
#                 bpm = 60 / np.mean(valid_intervals)  # Convert to beats per minute (bpm)
#                 self.heart_rate_label.setText(f"Heart rate: {bpm:.2f} bpm")
#             else:
#                 self.heart_rate_label.setText("Heart rate: 0 bpm")
#         else:
#             self.heart_rate_label.setText("Heart rate: 0 bpm")

#     def closeEvent(self, event):
#         self.data_collector.stop()   # Stop the data collector thread on close
#         self.data_collector.wait()  # Wait for the thread to finish
#         event.accept()  # Accept the close event

# def signal_handler(sig, frame):
#     print("Exiting...")
#     QtWidgets.QApplication.quit()

# if __name__ == "__main__":
#     signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C

#     streams = resolve_stream('name', 'BioAmpDataStream')
#     if not streams:
#         print("No LSL Stream found! Exiting...")
#         sys.exit(0)

#     app = QtWidgets.QApplication(sys.argv)
    
#     window = ECGApp()
#     window.setWindowTitle("Real-Time ECG Monitoring")
#     window.resize(800, 600)
#     window.show()

#     sys.exit(app.exec_())


import sys
import numpy as np
import time
from pylsl import StreamInlet, resolve_stream
from scipy.signal import butter, lfilter, iirnotch, find_peaks
import pyqtgraph as pg  # For real-time plotting
from pyqtgraph.Qt import QtWidgets, QtCore  # PyQt components for GUI
import signal  # For handling Ctrl+C
from collections import deque  # For creating a ring buffer

# Initialize global variables
inlet = None
data_buffer = np.zeros(2000)  # Buffer to hold the last 2000 samples for ECG data

# Function to design a Butterworth filter
def butter_filter(cutoff, fs, order=4, btype='low'):
    nyquist = 0.5 * fs  # Nyquist frequency
    normal_cutoff = cutoff / nyquist
    b, a = butter(order, normal_cutoff, btype=btype, analog=False)
    return b, a

# Apply the Butterworth filter to the data
def apply_filter(data, b, a):
    return lfilter(b, a, data)

# Notch filter for powerline interference removal
# def notch_filter(data, fs, freq=50.0, quality=30):
#     nyquist = 0.5 * fs
#     normal_cutoff = freq / nyquist
#     b, a = iirnotch(normal_cutoff, quality)
#     return lfilter(b, a, data)

# Function to detect heartbeats using peak detection
def detect_heartbeats(ecg_data, sampling_rate):
    peaks, _ = find_peaks(ecg_data, distance=sampling_rate * 0.6, prominence=0.5)  # Adjust as necessary
    return peaks

class DataCollector(QtCore.QThread):
    data_ready = QtCore.pyqtSignal(np.ndarray)

    def __init__(self):
        super().__init__()
        self.running = True
        self.sampling_rate = None

    def run(self):
        global inlet
        print("Looking for LSL stream...")
        streams = resolve_stream('name', 'BioAmpDataStream')
        
        if not streams:
            print("No LSL Stream found! Exiting...")
            sys.exit(0)

        inlet = StreamInlet(streams[0])
        self.sampling_rate = inlet.info().nominal_srate()
        print(f"Detected sampling rate: {self.sampling_rate} Hz")

        # Create filters
        low_cutoff = 20.0  # 40 Hz low-pass filter
        high_cutoff = 0.5  # 0.5 Hz high-pass filter
        notch_freq = 50.0  # Powerline interference at 50 Hz

        # Design the filters
        self.low_b, self.low_a = butter_filter(low_cutoff, self.sampling_rate, order=4, btype='low')
        # self.high_b, self.high_a = butter_filter(high_cutoff, self.sampling_rate, order=4, btype='high')
        # self.notch_b, self.notch_a = iirnotch(notch_freq / (0.5 * self.sampling_rate), 30)

        while self.running:
            # Pull multiple samples at once
            samples, _ = inlet.pull_chunk(timeout=0.0, max_samples=10)  # Pull up to 10 samples
            if samples:
                # Update data buffer
                global data_buffer
                data_buffer = np.roll(data_buffer, -len(samples))  # Shift data left
                data_buffer[-len(samples):] = [sample[0] for sample in samples]  # Add new samples to the end

                # Apply filters to the signal
                # filtered_data = apply_filter(data_buffer, self.high_b, self.high_a)  # High-pass
                filtered_data = apply_filter(data_buffer, self.low_b, self.low_a)   # Low-pass
                # filtered_data = apply_filter(filtered_data, self.notch_b, self.notch_a)  # Notch filter

                self.data_ready.emit(filtered_data)  # Emit the filtered data for plotting

            time.sleep(0.01)

    def stop(self):
        self.running = False

class ECGApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        # Create a plot widget
        self.plot_widget = pg.PlotWidget(title="ECG Signal")
        self.setCentralWidget(self.plot_widget)

        # Set background to white
        self.plot_widget.setBackground('w')

        # Create a label to display heart rate
        self.heart_rate_label = QtWidgets.QLabel("Heart rate: - bpm", self)
        self.heart_rate_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.heart_rate_label.setAlignment(QtCore.Qt.AlignCenter)

        # Layout
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.plot_widget)
        layout.addWidget(self.heart_rate_label)

        container = QtWidgets.QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.ecg_buffer = []    # Buffer to hold the ECG data
        self.r_peak_times = deque(maxlen=10)  # Ring buffer for R-peak timestamps

        # Data collector thread
        self.data_collector = DataCollector()
        self.data_collector.data_ready.connect(self.update_plot)
        self.data_collector.start()

        # Store the x-axis time window
        self.time_axis = np.linspace(0, 2000/200, 2000)  

        # Set fixed y-axis limits
        self.plot_widget.setYRange(-8000,16000)  # Adjust the range based on your ECG signal characteristics

    def update_plot(self, ecg_data):
        self.ecg_buffer = ecg_data  # Update buffer
        self.plot_widget.clear()
        # Set a fixed window (time axis) to ensure stable plotting
        self.plot_widget.plot(self.time_axis, self.ecg_buffer, pen='#000000')  # Plot ECG data with orange line
        self.plot_widget.setXRange(self.time_axis[0], self.time_axis[-1], padding=0)

        # Detect heartbeats in real time
        heartbeats = detect_heartbeats(np.array(self.ecg_buffer), self.data_collector.sampling_rate)

        # Debugging output
        print(f"Detected R-peaks at indices: {heartbeats}")  # Debug: print the indices of detected peaks

        # Append the actual time of detection for each detected peak
        for index in heartbeats:
            # Append the time based on the index and the sampling rate
            self.r_peak_times.append(index / self.data_collector.sampling_rate)

        self.calculate_heart_rate()   # Calculate heart rate after detecting R-peaks

    def calculate_heart_rate(self):
        if len(self.r_peak_times) > 1:
            # Calculate the time intervals between successive R-peaks
            intervals = np.diff(self.r_peak_times)

            # Debugging output
            print(f"R-peak times: {self.r_peak_times}")  # Log R-peak times
            print(f"Intervals between peaks: {intervals}")  # Log intervals

            # Filter intervals that are positive and non-zero to avoid issues
            valid_intervals = intervals[intervals > 0]

            if len(valid_intervals) > 0:
                bpm = 60 / np.mean(valid_intervals)  # Mean interval is in seconds, converting to bpm
                self.heart_rate_label.setText(f"Heart rate: {bpm:.2f} bpm")
            else:
                self.heart_rate_label.setText("Heart rate: 0 bpm")
        else:
            self.heart_rate_label.setText("Heart rate: 0 bpm")

    def closeEvent(self, event):
        self.data_collector.stop()   # Stop the data collector thread on close
        self.data_collector.wait()  # Wait for the thread to finish
        event.accept()  # Accept the close event

def signal_handler(sig, frame):
    print("Exiting...")
    QtWidgets.QApplication.quit()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C

    streams = resolve_stream('name', 'BioAmpDataStream')
    if not streams:
        print("No LSL Stream found! Exiting...")
        sys.exit(0)

    app = QtWidgets.QApplication(sys.argv)
    
    window = ECGApp()
    window.setWindowTitle("Real-Time ECG Monitoring")
    window.resize(800, 600)
    window.show()

    sys.exit(app.exec_())