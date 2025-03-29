from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import subprocess
import psutil
import signal
import sys
import atexit
import time
import os
import json
from threading import Thread

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

lsl_process = None
lsl_running = False
npg_running = False
npg_process = None
app_processes = {}
current_message = None
discovered_devices = []
npg_connection_thread = None

def is_process_running(name):
    for proc in psutil.process_iter(['pid', 'name']):
        if name in proc.info['name']:
            return True
    return False

@app.route("/")
def home():
    return render_template("index.html", lsl_started=lsl_running, npg_started=npg_running, running_apps=[k for k,v in app_processes.items() if v.poll() is None], message=current_message, devices=session.get('devices', []), selected_device=session.get('selected_device'))

@app.route("/scan_devices", methods=["POST"])
def scan_devices():
    global discovered_devices
    
    try:
        # Run the scanning in a separate process
        scan_process = subprocess.Popen([sys.executable, "npg-ble.py", "--scan"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Wait for scan to complete (with timeout)
        try:
            stdout, stderr = scan_process.communicate(timeout=10)
            if scan_process.returncode != 0:
                raise Exception(f"Scan failed: {stderr}")
            
            # Parse the output to get devices
            devices = []
            for line in stdout.split('\n'):
                if line.startswith("DEVICE:"):
                    parts = line[len("DEVICE:"):].strip().split('|')
                    if len(parts) >= 2:
                        devices.append({
                            "name": parts[0],
                            "address": parts[1]
                        })
            
            session['devices'] = devices
            discovered_devices = devices
            return jsonify({"status": "success", "devices": devices})
            
        except subprocess.TimeoutExpired:
            scan_process.kill()
            return jsonify({"status": "error", "message": "Device scan timed out"})
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/connect_device", methods=["POST"])
def connect_device():
    global npg_process, npg_running, npg_connection_thread
    
    device_address = request.form.get("device_address")
    if not device_address:
        return jsonify({"status": "error", "message": "No device selected"})
    
    session['selected_device'] = device_address
    
    def connect_and_monitor():
        global npg_process, npg_running, current_message
        
        try:
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "npg-ble.py")
            npg_process = subprocess.Popen([sys.executable, script_path, "--connect", device_address], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            
            # Monitor the output for connection status
            connected = False
            start_time = time.time()
            while time.time() - start_time < 10:  # 10 second timeout
                line = npg_process.stdout.readline()
                if not line:
                    break
                if "Connected to" in line:
                    connected = True
                    npg_running = True
                    current_message = f"Connected to {device_address}"
                    break
            
            if not connected:
                current_message = f"Failed to connect to {device_address}"
                if npg_process.poll() is None:
                    npg_process.terminate()
                npg_running = False
        
        except Exception as e:
            current_message = f"Connection error: {str(e)}"
            npg_running = False
    
    # Start the connection in a separate thread
    npg_connection_thread = Thread(target=connect_and_monitor)
    npg_connection_thread.start()
    
    return jsonify({"status": "pending"})

@app.route("/check_connection", methods=["GET"])
def check_connection():
    return jsonify({"connected": npg_running, "message": current_message})

@app.route("/start_lsl", methods=["POST"])
def start_lsl():
    global lsl_process, lsl_running, current_message
    save_csv = request.form.get('csv', 'false').lower() == 'true'

    if npg_running:
        current_message = "Please stop NPG stream first"
        return redirect(url_for('home'))

    if lsl_running:
        current_message = "LSL stream already running"
        return redirect(url_for('home'))

    try:
        command = ["python", "chords.py", "--lsl"]
        if save_csv:
            command.append("--csv")

        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        lsl_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation_flags, text=True, bufsize=1)

        time.sleep(2)
        output = lsl_process.stderr.readline().strip()
        if "No" in output:
            current_message = "Failed to start LSL stream"
            lsl_running = False
        else:
            current_message = "LSL stream started successfully"
            lsl_running = True

    except Exception as e:
        current_message = f"Error starting LSL: {str(e)}"
        lsl_running = False

    return redirect(url_for('home'))

@app.route("/start_npg", methods=["POST"])
def start_npg():
    global npg_process, npg_running, current_message

    if lsl_running:
        current_message = "Please stop LSL stream first"
        return redirect(url_for('home'))

    if npg_running:
        current_message = "NPG already running"
        return redirect(url_for('home'))

    try:
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "one.py")
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        
        npg_process = subprocess.Popen([sys.executable, script_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=creation_flags, text=True, bufsize=1, cwd=os.path.dirname(os.path.abspath(__file__)))

        start_time = time.time()
        connected = False
        while time.time() - start_time < 10:  # 10 second timeout
            line = npg_process.stdout.readline()
            if not line:
                break
            if "Connected to NPG-30:30:f9:f9:db:76" in line.strip():
                current_message = "NPG stream started successfully"
                npg_running = True
                connected = True
                break
        
        if not connected:
            current_message = "Failed to connect NPG stream (timeout)"
            npg_process.terminate()
            npg_running = False
            return redirect(url_for('home'))
        
        def consume_output():
            while npg_process.poll() is None:  # While process is running
                npg_process.stdout.readline()  # Keep reading to prevent buffer fill
        
        import threading
        output_thread = threading.Thread(target=consume_output, daemon=True)
        output_thread.start()
        
    except Exception as e:
        current_message = f"Error starting NPG: {str(e)}"
        npg_running = False
        if 'npg_process' in globals() and npg_process.poll() is None:
            npg_process.terminate()

    return redirect(url_for('home'))

@app.route("/run_app", methods=["POST"])
def run_app():
    global current_message
    app_name = request.form.get("app_name")
    valid_apps = ["heartbeat_ecg", "emgenvelope", "eog", "ffteeg", "game", "beetle", "gui", "keystroke", "csvplotter"]

    if not (lsl_running or npg_running):
        current_message = "Start LSL or NPG first!"
        return redirect(url_for('home'))

    if app_name not in valid_apps:
        current_message = "Invalid application"
        return redirect(url_for('home'))

    if app_name in app_processes and app_processes[app_name].poll() is None:
        current_message = f"{app_name} is already running"
        return redirect(url_for('home'))

    try:
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen(["python", f"{app_name}.py"], creationflags=creation_flags)
        
        app_processes[app_name] = process
        current_message = f"{app_name} started successfully"
    except Exception as e:
        current_message = f"Error starting {app_name}: {str(e)}"

    return redirect(url_for('home'))

@app.route("/stop_all", methods=['POST'])
def stop_all():
    global current_message
    stop_all_processes()
    current_message = "All processes stopped"
    return redirect(url_for('home'))

def cleanup_processes():
    global app_processes
    app_processes = {
        k: v for k, v in app_processes.items()
        if v.poll() is None  # Only keep running processes
    }

@app.route("/check_app_status", methods=["GET"])
def check_app_status():
    cleanup_processes()  # Remove finished processes
    return jsonify({"running_apps": list(app_processes.keys())})

def stop_all_processes():
    global lsl_process, npg_process, app_processes, lsl_running, npg_running, current_message

    # Terminate LSL process
    if lsl_process and lsl_process.poll() is None:
        lsl_process.terminate()
        try:
            lsl_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            lsl_process.kill()
        lsl_running = False

    if npg_process and npg_process.poll() is None:
        npg_process.terminate()
        try:
            npg_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            npg_process.kill()
        npg_running = False

    for app_name, process in list(app_processes.items()):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        del app_processes[app_name]

    print("All processes terminated.")

def handle_sigint(signal_num, frame):
    print("\nCtrl+C pressed! Stopping all processes...")
    stop_all_processes()
    sys.exit(0)

# Register signal handler for Ctrl+C
signal.signal(signal.SIGINT, handle_sigint)
atexit.register(stop_all_processes)

if __name__ == "__main__":
    app.run(debug=True)