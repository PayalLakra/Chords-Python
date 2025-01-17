import numpy as np
from collections import deque
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QMainWindow, QWidget
from PyQt5.QtCore import Qt
from pyqtgraph import PlotWidget
import pyqtgraph as pg
import pylsl
import sys
from scipy.signal import butter, filtfilt, iirnotch
from scipy.fft import fft

class EEGMonitor(QMainWindow):
    def __init__(self): 
        super().__init__()

        self.setWindowTitle("Real-Time EEG Monitor with FFT and Brainwave Power")
        self.setGeometry(100, 100, 1200, 800)

        # Main layout split into two halves: top for EEG, bottom for FFT and Brainwaves
        self.central_widget = QWidget()
        self.main_layout = QVBoxLayout(self.central_widget)

        # First half for EEG signal plot
        self.eeg_plot_widget = PlotWidget(self)
        self.eeg_plot_widget.setBackground('w')
        self.eeg_plot_widget.showGrid(x=True, y=True)
        self.eeg_plot_widget.setLabel('bottom', 'EEG Plot')
        self.eeg_plot_widget.setYRange(-5000, 5000, padding=0)
        self.eeg_plot_widget.setXRange(0, 2, padding=0)
        self.eeg_plot_widget.setMouseEnabled(x=False, y=True)  # Disable zoom
        self.main_layout.addWidget(self.eeg_plot_widget)

        # Second half for FFT and Brainwave Power, aligned horizontally
        self.bottom_layout = QHBoxLayout()

        # FFT Plot (left side of the second half)
        self.fft_plot = PlotWidget(self)
        self.fft_plot.setBackground('w')
        self.fft_plot.showGrid(x=True, y=True)
        self.fft_plot.setLabel('bottom', 'FFT')
        # self.fft_plot.setYRange(0, 25000, padding=0)
        self.fft_plot.setXRange(0, 50, padding=0)  # Set x-axis to 0 to 50 Hz
        self.fft_plot.setMouseEnabled(x=False, y=False)  # Disable zoom
        self.fft_plot.setAutoVisible(y=True)  # Allow y-axis to autoscale
        self.bottom_layout.addWidget(self.fft_plot)

        # Bar graph for brainwave power bands (right side of the second half)
        self.bar_chart_widget = pg.PlotWidget(self)
        self.bar_chart_widget.setBackground('w')
        self.bar_chart_widget.setLabel('bottom', 'Brainpower Bands')
        self.bar_chart_widget.setXRange(-0.5, 4.5)
        self.bar_chart_widget.setMouseEnabled(x=False, y=False)  # Disable zoom
        # Add brainwave power bars
        self.brainwave_bars = pg.BarGraphItem(x=[0, 1, 2, 3, 4], height=[0, 0, 0, 0, 0], width=0.5, brush='g')
        self.bar_chart_widget.addItem(self.brainwave_bars)
        # Set x-ticks for brainwave types
        self.bar_chart_widget.getAxis('bottom').setTicks([[(0, 'Delta'), (1, 'Theta'), (2, 'Alpha'), (3, 'Beta'), (4, 'Gamma')]])
        self.bottom_layout.addWidget(self.bar_chart_widget)

        # Add the bottom layout to the main layout
        self.main_layout.addLayout(self.bottom_layout)
        self.setCentralWidget(self.central_widget)

        # Set up LSL stream inlet
        streams = pylsl.resolve_stream('name', 'BioAmpDataStream')
        if not streams:
            print("No LSL stream found!")
            sys.exit(0)
        self.inlet = pylsl.StreamInlet(streams[0])

        # Sampling rate
        self.sampling_rate = int(self.inlet.info().nominal_srate())
        print(f"Sampling rate: {self.sampling_rate} Hz")

        # Data and Buffers
        self.filter_buffer_size = 30  # Minimum length for filtfilt
        self.filter_buffer = deque(maxlen=self.filter_buffer_size)
        self.one_second_buffer = deque(maxlen=self.sampling_rate)  # 1-second buffer
        self.buffer_size = self.sampling_rate * 10
        self.moving_window_size = self.sampling_rate * 2  # 2-second window

        self.eeg_data = np.zeros(self.buffer_size)
        self.time_data = np.linspace(0, 10, self.buffer_size)
        self.current_index = 0

        self.b_notch, self.a_notch = iirnotch(50, 30, self.sampling_rate)
        self.b_band, self.a_band = butter(4, [0.5 / (self.sampling_rate / 2), 48.0 / (self.sampling_rate / 2)], btype='band')

        # Timer for updating the plot
        self.timer = pg.QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(20) 

        self.eeg_curve = self.eeg_plot_widget.plot(self.time_data, self.eeg_data, pen=pg.mkPen('b', width=1))  #EEG Colour is blue
        self.fft_curve = self.fft_plot.plot(pen=pg.mkPen('r', width=1))  # FFT Colour is red

    def update_plot(self):
        samples, _ = self.inlet.pull_chunk(timeout=0.0)
        if samples:
            for sample in samples:
                raw_point = sample[0]
                self.filter_buffer.append(raw_point)

                # Apply the filters if the buffer is full
                if len(self.filter_buffer) == self.filter_buffer_size:
                    notch_filtered = filtfilt(self.b_notch, self.a_notch, list(self.filter_buffer))[-1]
                    band_filtered = filtfilt(self.b_band, self.a_band, list(self.filter_buffer))[-1]
                else:
                    continue

                self.eeg_data[self.current_index] = band_filtered               # Plot the filtered data
                self.current_index = (self.current_index + 1) % self.buffer_size

                if self.current_index == 0:
                    plot_data = self.eeg_data
                else:
                    plot_data = np.concatenate((self.eeg_data[self.current_index:], self.eeg_data[:self.current_index]))

                recent_data = plot_data[-self.moving_window_size:]
                recent_time = np.linspace(0, len(recent_data) / self.sampling_rate, len(recent_data))
                self.eeg_curve.setData(recent_time, recent_data)

                self.one_second_buffer.append(band_filtered)           # Add the filtered point to the 1-second buffer
                if len(self.one_second_buffer) == self.sampling_rate:  # Process FFT and brainwave power
                    self.process_fft_and_brainpower()
                    self.one_second_buffer.clear() 
                    
    def process_fft_and_brainpower(self):
        window = np.hanning(len(self.one_second_buffer))       # Apply Hanning window to the buffer
        buffer_windowed = np.array(self.one_second_buffer) * window

        # Perform FFT
        fft_result = np.abs(fft(buffer_windowed))[:len(buffer_windowed) // 2]
        fft_result /= len(buffer_windowed)
        freqs = np.fft.fftfreq(len(buffer_windowed), 1 / self.sampling_rate)[:len(buffer_windowed) // 2]
        self.fft_curve.setData(freqs, fft_result)

        brainwave_power = self.calculate_brainwave_power(fft_result, freqs)
        self.brainwave_bars.setOpts(height=brainwave_power)

    def calculate_brainwave_power(self, fft_data, freqs):
        delta_power = np.sum(fft_data[(freqs >= 0.5) & (freqs <= 4)] ** 2)
        theta_power = np.sum(fft_data[(freqs >= 4) & (freqs <= 8)] ** 2)
        alpha_power = np.sum(fft_data[(freqs >= 8) & (freqs <= 13)] ** 2)
        beta_power = np.sum(fft_data[(freqs >= 13) & (freqs <= 30)] ** 2)
        gamma_power = np.sum(fft_data[(freqs >= 30) & (freqs <= 45)] ** 2)

        return [delta_power, theta_power, alpha_power, beta_power, gamma_power]
 
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EEGMonitor()  
    window.show()
    sys.exit(app.exec_())