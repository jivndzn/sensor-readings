import serial
import requests
import time
import json

# ========== 1) Supabase Info ==========
supabase_url = "https://exkuzazecthqeoogpsfn.supabase.co/rest/v1/sensor_readings"
supabase_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV4a3V6YXplY3RocWVvb2dwc2ZuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDIyOTIzOTUsImV4cCI6MjA1Nzg2ODM5NX0.f8-TBMIsFDv773uNzRNxycJyVgZY4vIRANLxsol0y5Y"

headers = {
    "Content-Type": "application/json",
    "apikey": supabase_key,
    "Authorization": f"Bearer {supabase_key}",
    "Prefer": "return=minimal"  # Don't return the inserted row
}

# ========== 2) Serial Port Setup ==========
SERIAL_PORT = "COM8"  # Updated to match your detected port
BAUD_RATE = 9600

# Try to automatically find the Arduino port
try:
    import serial.tools.list_ports
    auto_port = find_arduino_port()
    if auto_port:
        SERIAL_PORT = auto_port
        print(f"Automatically detected Arduino at {SERIAL_PORT}")
except ImportError:
    print("Serial port tools not available. Using configured port.")

# Open the serial port with proper resource management
ser = None
try:
    # First check if port is already open
    try:
        test_port = serial.Serial(SERIAL_PORT)
        test_port.close()
    except serial.SerialException:
        pass  # Port is available
        
    # Now try to open it for our use
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print(f"Connected to {SERIAL_PORT} at {BAUD_RATE} baud.")
    time.sleep(2)  # Wait for Arduino to reset after connection
    
except serial.SerialException as e:
    print(f"Error opening serial port {SERIAL_PORT}: {e}")
    print("Troubleshooting steps:")
    print("1. Make sure no other program is using the port")
    print("2. Run the script as administrator")
    print("3. Verify the correct COM port in Device Manager")
    print("4. Try unplugging and replugging the Arduino")
    if ser:
        ser.close()
    exit(1)

# ========== 3) Read & Upload Loop ==========
reading_buffer = []  # Store readings in case of connection issues
MAX_BUFFER_SIZE = 10  # Maximum number of readings to store before trying to send again

print("Waiting for data from Arduino...")

while True:
    try:
        # Read one line from the serial port
        line = ser.readline().decode('utf-8', errors='replace').strip()
        
        # Skip empty lines or debug output (which contains characters like ':')
        if not line or ":" in line:
            continue
            
        # Try to parse CSV: "temperature,ph,quality"
        try:
            values = line.split(",")
            if len(values) == 3:
                temperature = float(values[0])
                ph = float(values[1])
                quality = float(values[2])
                
                # Basic validation
                if -20 <= temperature <= 100 and 0 <= ph <= 14 and 0 <= quality <= 100:
                    data_source = "arduino_uno"
                    
                    # Prepare JSON payload
                    payload = {
                        "temperature": temperature,
                        "pH": ph,
                        "quality": quality,
                        "data_source": data_source
                    }
                    
                    print(f"Received valid data: Temp={temperature}°C, pH={ph}, Quality={quality}")
                    
                    # Try to send to Supabase
                    try:
                        response = requests.post(supabase_url, json=payload, headers=headers, timeout=5)
                        
                        if response.status_code in (200, 201):
                            print(f"✓ Data successfully inserted into Supabase")
                            
                            # If we had buffered readings, try to send them now
                            if reading_buffer:
                                print(f"Attempting to send {len(reading_buffer)} buffered readings...")
                                for buffered_payload in reading_buffer[:]:  # Use a copy for iteration
                                    try:
                                        buffer_response = requests.post(supabase_url, json=buffered_payload, headers=headers, timeout=5)
                                        if buffer_response.status_code in (200, 201):
                                            reading_buffer.remove(buffered_payload)
                                            print(f"✓ Buffered reading sent successfully")
                                        else:
                                            print(f"× Failed to send buffered reading: {buffer_response.status_code}")
                                    except requests.RequestException:
                                        # Keep it in buffer
                                        pass
                        else:
                            print(f"× Insert failed ({response.status_code}): {response.text}")
                            # Buffer the reading for later
                            reading_buffer.append(payload)
                            if len(reading_buffer) > MAX_BUFFER_SIZE:
                                reading_buffer.pop(0)  # Remove oldest if buffer is full
                            
                    except requests.RequestException as e:
                        print(f"× Network error: {e}")
                        # Buffer the reading for later
                        reading_buffer.append(payload)
                        if len(reading_buffer) > MAX_BUFFER_SIZE:
                            reading_buffer.pop(0)  # Remove oldest if buffer is full
                else:
                    print(f"× Invalid data range: Temp={temperature}°C, pH={ph}, Quality={quality}")
            else:
                # Skip lines that aren't valid data
                pass
                
        except ValueError as e:
            # Not valid CSV data, probably debug output or malformed line
            pass
                
    except Exception as e:
        print(f"× Error: {e}")

    # Short delay
    time.sleep(0.1)
    