import serial
import requests
import time
import json
from datetime import datetime
from typing import Dict, Any, Optional
import pytz

# Supabase configuration
SUPABASE_URL = "https://exkuzazecthqeoogpsfn.supabase.co/rest/v1/sensor_readings"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV4a3V6YXplY3RocWVvb2dwc2ZuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDIyOTIzOTUsImV4cCI6MjA1Nzg2ODM5NX0.f8-TBMIsFDv773uNzRNxycJyVgZY4vIRANLxsol0y5Y"

PH_TZ = pytz.timezone('Asia/Manila')

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
        finally:
            if 'ser' in locals():
                ser.close()

if __name__ == "__main__":
    collector = SensorDataCollector()
    collector.run()