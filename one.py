import asyncio
from bleak import BleakScanner, BleakClient
import time
from pylsl import StreamInfo, StreamOutlet

# BLE parameters (must match your firmware)
DEVICE_NAME = "NPG-30:30:f9:f9:db:76"
SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
DATA_CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
CONTROL_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"

# Packet parameters for batched samples:
SINGLE_SAMPLE_LEN = 7              # Each sample is 7 bytes
BLOCK_COUNT = 10                   # Batch size: 10 samples per notification
NEW_PACKET_LEN = SINGLE_SAMPLE_LEN * BLOCK_COUNT  # Total packet length (70 bytes)

# Set up an LSL stream with int16 data format (irregular rate)
stream_name = "NPG"
info = StreamInfo(stream_name, "EXG", 3, 500, "int16", "uid007")
outlet = StreamOutlet(info)

# Global variables for unrolled counter, sample counting, and timing
prev_unrolled_counter = None  # Unrolled (cumulative) counter from firmware
samples_received = 0          # Total samples received in the last second
start_time = None             # Time when first sample is received
total_missing_samples = 0

def process_sample(sample_data: bytearray):
    global prev_unrolled_counter, samples_received, start_time, total_missing_samples
    if len(sample_data) != SINGLE_SAMPLE_LEN:
        print("Unexpected sample length:", len(sample_data))
        return
    sample_counter = sample_data[0]
    # Unroll the counter:
    if prev_unrolled_counter is None:
        prev_unrolled_counter = sample_counter
    else:
        last = prev_unrolled_counter % 256
        if sample_counter < last:
            current_unrolled = prev_unrolled_counter - last + sample_counter + 256
        else:
            current_unrolled = prev_unrolled_counter - last + sample_counter
        if current_unrolled != prev_unrolled_counter + 1:
            print(f"Missing sample: expected {prev_unrolled_counter + 1}, got {current_unrolled}")
            total_missing_samples += current_unrolled - (prev_unrolled_counter + 1)
        prev_unrolled_counter = current_unrolled

    # Set start_time when first sample is received
    if start_time is None:
        start_time = time.time()
    elapsed = time.time() - start_time

    channels = []
    for ch in range(3):
        offset = 1 + ch * 2
        value = int.from_bytes(sample_data[offset:offset+2], byteorder='big', signed=True)
        channels.append(value)
    print(f"Sample {prev_unrolled_counter} at {elapsed:.2f} s: Channels: {channels} Total missing samples: {total_missing_samples}")
    outlet.push_sample(channels)
    samples_received += 1

def notification_handler(sender, data: bytearray):
    if len(data) == NEW_PACKET_LEN:
        for i in range(0, NEW_PACKET_LEN, SINGLE_SAMPLE_LEN):
            sample = data[i:i+SINGLE_SAMPLE_LEN]
            process_sample(sample)
    elif len(data) == SINGLE_SAMPLE_LEN:
        process_sample(data)
    else:
        print("Unexpected packet length:", len(data))

async def print_rate():
    global samples_received
    while True:
        await asyncio.sleep(1)
        print(f"Samples per second: {samples_received}")
        samples_received = 0

async def run():
    print("Scanning for BLE devices with name starting with", DEVICE_NAME)
    devices = await BleakScanner.discover()
    target = None
    for d in devices:
        if d.name and DEVICE_NAME.lower() in d.name.lower():
            target = d
            break
    if target is None:
        print("No target device found")
        return

    print("Connecting to:", target.name, target.address)
    async with BleakClient(target) as client:
        if not client.is_connected:
            print("Failed to connect")
            return
        print("Connected to", target.name)
        await client.write_gatt_char(CONTROL_CHAR_UUID, b"START", response=True)
        print("Sent START command")
        await client.start_notify(DATA_CHAR_UUID, notification_handler)
        print("Subscribed to data notifications")
        asyncio.create_task(print_rate())
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(run())