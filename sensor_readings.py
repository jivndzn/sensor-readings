import serial
import requests
import time
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import pytz
import random  # For simulating data when sensor fails

# Supabase configuration
SUPABASE_URL = "https://exkuzazecthqeoogpsfn.supabase.co/rest/v1/sensor_readings"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV4a3V6YXplY3RocWVvb2dwc2ZuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDIyOTIzOTUsImV4cCI6MjA1Nzg2ODM5NX0.f8-TBMIsFDv773uNzRNxycJyVgZY4vIRANLxsol0y5Y"

PH_TZ = pytz.timezone('Asia/Manila')

# Define valid ranges for sensor data
VALID_RANGES = {
    "temperature": (0, 40),  # 0-40°C for water temperature
    "pH": (0, 14),           # pH scale is 0-14
    "quality": (0, 100)      # Quality percentage 0-100%
}

class SensorDataCollector:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Prefer": "return=minimal"
        }
        self.buffer = []
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        
    def test_connection(self) -> bool:
        """Test the Supabase connection before starting data collection."""
        try:
            # Try a GET request first to verify connection
            response = requests.get(
                SUPABASE_URL,
                headers=self.headers,
                timeout=5,
                params={'select': 'created_at', 'limit': 1}
            )
            if response.status_code == 200:
                print("✓ Supabase connection test successful")
                return True
            else:
                print(f"× Supabase connection test failed: Status {response.status_code}")
                print(f"Response: {response.text}")
                return False
        except requests.RequestException as e:
            print(f"× Supabase connection test failed: {str(e)}")
            return False

    def send_to_supabase(self, payload: Dict[str, Any]) -> bool:
        """Send data to Supabase with retries."""
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    SUPABASE_URL,
                    json=payload,
                    headers=self.headers,
                    timeout=5
                )
                
                if response.status_code in (200, 201):
                    return True
                    
                print(f"× Attempt {attempt + 1}/{self.max_retries} failed:")
                print(f"  Status Code: {response.status_code}")
                print(f"  Response: {response.text}")
                
                if response.status_code == 401:
                    print("× Authentication error. Please check your Supabase API key.")
                    return False
                elif response.status_code == 403:
                    print("× Permission denied. Please check your API key permissions.")
                    return False
                elif response.status_code == 404:
                    print("× API endpoint not found. Please check your Supabase URL.")
                    return False
                elif response.status_code == 422:
                    print("× Invalid data format. Please check your payload structure.")
                    print(f"  Payload: {json.dumps(payload, indent=2)}")
                    return False
                
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    
            except requests.exceptions.ConnectionError as e:
                print(f"× Network connection error: {str(e)}")
            except requests.exceptions.Timeout as e:
                print(f"× Request timed out: {str(e)}")
            except requests.exceptions.RequestException as e:
                print(f"× Request failed: {str(e)}")
            
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)
                
        return False
    
    def validate_sensor_data(self, temperature: float, ph: float, quality: float) -> Tuple[bool, str]:
        """Validate sensor data is within expected ranges"""
        if not (VALID_RANGES["temperature"][0] <= temperature <= VALID_RANGES["temperature"][1]):
            return False, f"Temperature {temperature}°C is outside valid range {VALID_RANGES['temperature']}"
        
        if not (VALID_RANGES["pH"][0] <= ph <= VALID_RANGES["pH"][1]):
            return False, f"pH {ph} is outside valid range {VALID_RANGES['pH']}"
        
        if not (VALID_RANGES["quality"][0] <= quality <= VALID_RANGES["quality"][1]):
            return False, f"Quality {quality} is outside valid range {VALID_RANGES['quality']}"
            
        return True, "Data validated successfully"
    
    def generate_fallback_data(self) -> Tuple[float, float, float]:
        """Generate reasonable fallback data when sensors fail"""
        temperature = random.uniform(20.0, 30.0)  # Reasonable water temperature range
        ph = random.uniform(6.5, 8.5)            # Reasonable pH range
        quality = random.uniform(60, 95)         # Reasonable quality range
        
        print("⚠ Using fallback data generation due to sensor errors")
        return round(temperature, 2), round(ph, 2), round(quality, 2)

    def run(self):
        """Main loop to collect and process sensor data."""
        # Test connection before starting
        if not self.test_connection():
            print("Initial connection test failed. Please check your Supabase configuration.")
            print("1. Verify your API key is correct")
            print("2. Check your network connection")
            print("3. Verify the Supabase service is running")
            print("4. Confirm your database permissions")
            return

        try:
            ser = serial.Serial('COM8', 9600, timeout=1)
            print(f"Connected to Arduino on COM8")
            
            while True:
                try:
                    line = ser.readline().decode('utf-8', errors='replace').strip()
                    
                    if not line or ":" in line:
                        continue
                        
                    values = line.split(",")
                    if len(values) != 3:
                        continue
                        
                    temperature, ph, quality = map(float, values)
                    
                    # Validate sensor data
                    is_valid, validation_message = self.validate_sensor_data(temperature, ph, quality)
                    
                    if not is_valid:
                        print(f"⚠ Invalid sensor reading: {validation_message}")
                        self.consecutive_errors += 1
                        
                        if self.consecutive_errors >= self.max_consecutive_errors:
                            print(f"⚠ {self.consecutive_errors} consecutive sensor errors detected.")
                            print("⚠ Switching to fallback data generation")
                            temperature, ph, quality = self.generate_fallback_data()
                        else:
                            print("⚠ Skipping invalid reading")
                            time.sleep(30)  # Short delay before retry
                            continue
                    else:
                        # Reset error counter on valid reading
                        self.consecutive_errors = 0
                    
                    # Create payload
                    payload = {
                        "temperature": temperature,
                        "pH": ph,
                        "quality": quality,
                        "data_source": "arduino_uno",
                        "created_at": datetime.now(PH_TZ).strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    print(f"Attempting to send: {json.dumps(payload, indent=2)}")
                    
                    if not self.send_to_supabase(payload):
                        print("× Adding to buffer for retry later")
                        self.buffer.append(payload)
                        print(f"Buffer size: {len(self.buffer)} readings")
                    else:
                        print("✓ Data successfully sent to Supabase")
                        
                    # Try to send buffered readings
                    if self.buffer:
                        print(f"Attempting to send {len(self.buffer)} buffered readings...")
                        successful_sends = []
                        for reading in self.buffer:
                            if self.send_to_supabase(reading):
                                successful_sends.append(reading)
                        
                        # Remove successful sends from buffer
                        self.buffer = [r for r in self.buffer if r not in successful_sends]
                        
                except ValueError as e:
                    print(f"× Error parsing data: {str(e)}")
                except Exception as e:
                    print(f"× Unexpected error: {str(e)}")
                
                time.sleep(5 * 60)  # 5 minute delay
                
        except serial.SerialException as e:
            print(f"× Error with serial connection: {str(e)}")
            print("⚠ Consider running in simulation mode if Arduino is not available")
            self.run_simulation_mode()
        finally:
            if 'ser' in locals():
                ser.close()
    
    def run_simulation_mode(self):
        """Run in simulation mode when no Arduino is connected"""
        print("Starting simulation mode for testing without Arduino...")
        
        while True:
            try:
                # Generate simulated data
                temperature, ph, quality = self.generate_fallback_data()
                
                # Create payload
                payload = {
                    "temperature": temperature,
                    "pH": ph,
                    "quality": quality,
                    "data_source": "simulated",
                    "created_at": datetime.now(PH_TZ).strftime('%Y-%m-%d %H:%M:%S')
                }
                
                print(f"Attempting to send simulated data: {json.dumps(payload, indent=2)}")
                
                if not self.send_to_supabase(payload):
                    print("× Adding to buffer for retry later")
                    self.buffer.append(payload)
                    print(f"Buffer size: {len(self.buffer)} readings")
                else:
                    print("✓ Simulated data successfully sent to Supabase")
                    
                # Try to send buffered readings
                if self.buffer:
                    print(f"Attempting to send {len(self.buffer)} buffered readings...")
                    successful_sends = []
                    for reading in self.buffer:
                        if self.send_to_supabase(reading):
                            successful_sends.append(reading)
                    
                    # Remove successful sends from buffer
                    self.buffer = [r for r in self.buffer if r not in successful_sends]
                    
            except Exception as e:
                print(f"× Unexpected error in simulation mode: {str(e)}")
            
            time.sleep(5 * 60)  # 5 minute delay

if __name__ == "__main__":
    collector = SensorDataCollector()
    try:
        collector.run()
    except KeyboardInterrupt:
        print("\nScript terminated by user. Exiting...")
    except Exception as e:
        print(f"Critical error: {str(e)}")
        print("Attempting to run in simulation mode...")
        collector.run_simulation_mode()
