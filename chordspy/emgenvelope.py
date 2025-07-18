import numpy as np
from scipy.signal import butter, filtfilt
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QMainWindow, QWidget
from pyqtgraph import PlotWidget
import pyqtgraph as pg
import pylsl
import sys
import time

class EMGMonitor(QMainWindow):
    def __init__(self): 
        super().__init__()

        self.setWindowTitle("Real-Time EMG Monitor with EMG Envelope")
        self.setGeometry(100, 100, 800, 600)

        self.stream_active = True  # Flag to check if the stream is active
        self.last_data_time = None  # Variable to store the last data time

        # Create layout
        layout = QVBoxLayout()

        # Create plot widgets for Filtered EMG and EMG envelope
        self.emg_plot = PlotWidget(self)
        self.emg_plot.setBackground('w')
        self.emg_plot.showGrid(x=True, y=True)
        self.emg_plot.setMouseEnabled(x=False, y=False)  # Disable zoom
        self.emg_plot.setTitle("Filtered EMG Signal (High Pass:70 Hz)")

        self.envelope_plot = PlotWidget(self)
        self.envelope_plot.setBackground('w')
        self.envelope_plot.showGrid(x=True, y=True)
        self.envelope_plot.setMouseEnabled(x=False, y=False)  # Disable zoom
        self.envelope_plot.setTitle("EMG Envelope (Samples Average:10%)")

        # Add plots to layout
        layout.addWidget(self.emg_plot)
        layout.addWidget(self.envelope_plot)

        # Central widget
        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # Set up LSL stream inlet
        print("Searching for available LSL streams...")
        available_streams = pylsl.resolve_streams()

        if not available_streams:
            print("No LSL streams found! Exiting...")
            sys.exit(0)

        self.inlet = None
        for stream in available_streams:
            try:
                self.inlet = pylsl.StreamInlet(stream)
                print(f"Connected to LSL stream: {stream.name()}")
                break
            except Exception as e:
                print(f"Failed to connect to {stream.name()}: {e}")

        if self.inlet is None:
            print("Unable to connect to any LSL stream! Exiting...")
            sys.exit(0)

        # Sampling rate
        self.sampling_rate = int(self.inlet.info().nominal_srate())
        print(f"Sampling rate: {self.sampling_rate} Hz")
        
        # Data and buffers
        self.buffer_size = self.sampling_rate * 10  # Fixed-size buffer for 10 seconds
        self.emg_data = np.zeros(self.buffer_size)  # Fixed-size array for circular buffer
        self.time_data = np.linspace(0, 10, self.buffer_size)  # Fixed time array for plotting
        self.current_index = 0  # Index for overwriting data

        self.b, self.a = butter(4, 70.0 / (0.5 * self.sampling_rate), btype='high')

        # Moving RMS window size (25 for 250 sampling rate and 50 for 500 sampling rate)
        self.rms_window_size = int(0.1 * self.sampling_rate)

        # Set fixed axis ranges
        self.emg_plot.setXRange(0, 10, padding=0)
        self.envelope_plot.setXRange(0, 10, padding=0)

        # Set y-axis limits based on sampling rate for Filtered EMG
        if self.sampling_rate == 250:  
            self.emg_plot.setYRange(-((2**10)/2), ((2**10)/2), padding=0)  # for R3
            self.envelope_plot.setYRange(0, ((2**10)/2), padding=0)  # for R3
        elif self.sampling_rate == 500:  
            self.emg_plot.setYRange(-((2**14)/2), ((2**14)/2), padding=0)  # for R4
            self.envelope_plot.setYRange(0, ((2**14)/2), padding=0)  # for R4

        # Plot curves for EMG data and envelope
        self.emg_curve = self.emg_plot.plot(self.time_data, self.emg_data, pen=pg.mkPen('b', width=1))
        self.envelope_curve = self.envelope_plot.plot(self.time_data, self.emg_data, pen=pg.mkPen('r', width=2))

        # Timer for plot update
        self.timer = pg.QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(15)

    def calculate_moving_rms(self, signal, window_size):
        # Calculate RMS using a moving window
        rms = np.sqrt(np.convolve(signal**2, np.ones(window_size) / window_size, mode='valid'))
        return np.pad(rms, (len(signal) - len(rms), 0), 'constant')

    def update_plot(self):
        global last_data_time, stream_active
        if self.inlet is None or not self.stream_active:
            return
        samples, _ = self.inlet.pull_chunk(timeout=0.0, max_samples=30)
        if samples:
            self.last_data_time = time.time()
            for sample in samples:
                # Overwrite the oldest data point in the buffer
                self.emg_data[self.current_index] = sample[0]
                self.current_index = (self.current_index + 1) % self.buffer_size  # Circular increment

            # Filter the EMG data
            filtered_emg = filtfilt(self.b, self.a, self.emg_data)

            # Take absolute value before calculating RMS envelope
            abs_filtered_emg = np.abs(filtered_emg)

            # Calculate the RMS envelope
            rms_envelope = self.calculate_moving_rms(abs_filtered_emg, self.rms_window_size)

            # Update curves
            self.emg_curve.setData(self.time_data, filtered_emg)  # Plot filtered EMG in blue
            self.envelope_curve.setData(self.time_data, rms_envelope)  # Plot EMG envelope in red

        else:
            if self.last_data_time and (time.time() - self.last_data_time) > 2:
                self.stream_active = False
                print("LSL stream disconnected!")
                self.timer.stop()
                self.close()
                  
def main():
    app = QApplication(sys.argv)
    window = EMGMonitor()  
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()