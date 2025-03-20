import serial
import requests
import time
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import pytz

# Configuration
SUPABASE_URL = "https://exkuzazecthqeoogpsfn.supabase.co/rest/v1/sensor_readings"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV4a3V6YXplY3RocWVvb2dwc2ZuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDIyOTIzOTUsImV4cCI6MjA1Nzg2ODM5NX0.f8-TBMIsFDv773uNzRNxycJyVgZY4vIRANLxsol0y5Y"
PH_TZ = pytz.timezone('Asia/Manila')

# Current session info
CURRENT_UTC_TIME = "2025-03-20 07:16:22"
CURRENT_USER = "jivndzn"

# Calibration constants
TEMP_CALIBRATION_FACTOR = 0.294  # Convert from 85°C to ~25°C
TEMP_OFFSET = 0
PH_OFFSET = 0

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

        print(f"Initializing sensor data collection system")
        print(f"Current UTC time: {CURRENT_UTC_TIME}")
        print(f"Session user: {CURRENT_USER}")
        print(f"Temperature calibration: factor={TEMP_CALIBRATION_FACTOR}, offset={TEMP_OFFSET}")
        print(f"pH calibration: {PH_OFFSET} offset applied to match detector")
        
        # Calibration ranges
        self.ph_ranges = {
            "Domestic Household Use": (6.5, 8.5),
            "Plant Irrigation": [(5.5, 6.5), (8.5, 9.0)],
            "Non-potable Applications": [(0, 5.5), (9.0, 14)]
        }
        
        self.quality_ranges = {
            "Poor": (90, 100),
            "Fair": (70, 90),
            "Good": (40, 70),
            "Excellent": (0, 40)
        }
        
        self.turbidity_ranges = {
            "Very Dirty": (90, 100),
            "Dirty": (80, 90),
            "Slightly Dirty": (70, 80),
            "Very Cloudy": (60, 70),
            "Cloudy": (50, 60),
            "Slightly Cloudy": (40, 50),
            "Clear": (0, 40)
        }

    def validate_and_calibrate(self, temperature: float, ph: float, quality: float) -> Tuple[float, float, float]:
        """Validate and calibrate sensor readings."""
        # Temperature calibration
        raw_temp = temperature
        # Apply calibration factor and offset
        temperature = (temperature * TEMP_CALIBRATION_FACTOR) + TEMP_OFFSET
        
        # Temperature validation
        if not (0 <= temperature <= 40):
            print(f"⚠️ Temperature reading out of expected range: {temperature}°C")
            temperature = max(0, min(40, temperature))

        # Log temperature calibration
        print(f"Temperature Calibration:")
        print(f"├─ Raw reading: {raw_temp:.1f}°C")
        print(f"├─ Calibration factor: {TEMP_CALIBRATION_FACTOR}")
        print(f"├─ Offset: {TEMP_OFFSET}")
        print(f"└─ Calibrated: {temperature:.1f}°C")

        # pH calibration
        raw_ph = ph
        ph = ph + PH_OFFSET  # Apply offset

        # Temperature compensation for pH (using calibrated temperature)
        temp_coefficient = 0.03  # pH change per degree C
        temp_compensation = (temperature - 25) * temp_coefficient
        
        # Apply temperature compensation to pH
        calibrated_ph = ph + temp_compensation

        # Ensure valid pH range
        calibrated_ph = max(0, min(14, calibrated_ph))
        
        # Detailed pH logging
        print(f"pH Calibration:")
        print(f"├─ Original reading: {raw_ph:.2f}")
        print(f"├─ After offset: {ph:.2f}")
        print(f"├─ Temperature compensation: {temp_compensation:.3f}")
        print(f"└─ Final calibrated pH: {calibrated_ph:.2f}")
        
        # Print recommendations
        self.print_ph_recommendations(calibrated_ph)

        # Quality validation
        if not (0 <= quality <= 100):
            print(f"⚠️ Quality reading out of expected range: {quality}%")
            quality = max(0, min(quality, 100))

        return temperature, calibrated_ph, quality

    def print_ph_recommendations(self, ph: float):
        """Print recommendations based on calibrated pH value."""
        recommendations = {
            (0, 3): "Extremely acidic - Caution required",
            (3, 4): "Very acidic - Typical for vinegar and citrus fruits",
            (4, 5): "Acidic - Similar to tomato juice and beer",
            (5, 6): "Slightly acidic - Similar to coffee and tea",
            (6, 7): "Near neutral - Safe for most uses",
            (7, 7.5): "Neutral - Ideal for drinking water",
            (7.5, 8.5): "Slightly alkaline - Acceptable for drinking water",
            (8.5, 10): "Alkaline - May have soap-like taste",
            (10, 14): "Very alkaline - Caution required"
        }
        
        for (lower, upper), message in recommendations.items():
            if lower <= ph < upper:
                print(f"pH Range {lower}-{upper}: {message}")
                break

    def get_water_use_recommendation(self, ph: float) -> str:
        if 6.5 <= ph <= 8.5:
            return "Domestic Household Use"
        elif (5.5 <= ph < 6.5) or (8.5 < ph <= 9.0):
            return "Plant Irrigation"
        else:
            return "Non-potable Applications"
    
    def get_quality_description(self, quality: float) -> str:
        if quality >= 90:
            return "Poor"
        elif quality >= 70:
            return "Fair"
        elif quality >= 40:
            return "Good"
        else:
            return "Excellent"
    
    def get_turbidity_description(self, quality: float) -> str:
        if quality >= 90:
            return "Very Dirty"
        elif quality >= 80:
            return "Dirty"
        elif quality >= 70:
            return "Slightly Dirty"
        elif quality >= 60:
            return "Very Cloudy"
        elif quality >= 50:
            return "Cloudy"
        elif quality >= 40:
            return "Slightly Cloudy"
        else:
            return "Clear"
    
    def get_turbidity_recommendation(self, quality: float) -> str:
        inverted_quality = 100 - quality
        
        if inverted_quality >= 90:
            return "Not suitable for any domestic or agricultural use"
        elif inverted_quality >= 80:
            return "Not recommended for household use, limited agricultural applications"
        elif inverted_quality >= 70:
            return "Requires significant treatment before any use"
        elif inverted_quality >= 60:
            return "Suitable for watering non-edible plants, not for consumption"
        elif inverted_quality >= 50:
            return "Suitable for irrigation and non-contact use"
        elif inverted_quality >= 40:
            return "Safe for bathing and laundry, requires filtration for drinking"
        else:
            return "Safe for drinking after basic treatment"
    
    def test_connection(self) -> bool:
        try:
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
        if not self.test_connection():
            print("Initial connection test failed. Please check your Supabase configuration.")
            print("1. Verify your API key is correct")
            print("2. Check your network connection")
            print("3. Verify the Supabase service is running")
            print("4. Confirm your database permissions")
            return

        serial_connection = None
        try:
            serial_connection = serial.Serial('COM8', 9600, timeout=1)
            print(f"Connected to Arduino on COM8")
            
            while True:
                try:
                    line = serial_connection.readline().decode('utf-8', errors='replace').strip()
                    
                    if not line or ":" in line:
                        continue
                        
                    values = line.split(",")
                    if len(values) != 3:
                        continue
                        
                    temperature, ph, quality = map(float, values)
                    
                    # Validate and calibrate readings
                    temperature, ph, quality = self.validate_and_calibrate(temperature, ph, quality)
                    
                    # Get interpretations
                    water_use = self.get_water_use_recommendation(ph)
                    quality_desc = self.get_quality_description(quality)
                    turbidity_desc = self.get_turbidity_description(quality)
                    turbidity_rec = self.get_turbidity_recommendation(quality)
                    
                    # Create payload - matching database schema
                    payload = {
                        "temperature": temperature,
                        "pH": ph,
                        "quality": quality,
                        "data_source": "arduino_uno",
                        "created_at": datetime.now(PH_TZ).strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    print(f"Sensor readings: Temp={temperature:.1f}°C, pH={ph:.2f}, Quality={quality:.1f}%")
                    print(f"Interpretation: {quality_desc} water quality, {turbidity_desc} turbidity")
                    print(f"Recommendation: {water_use}, {turbidity_rec}")
                    print(f"Attempting to send data...")
                    
                    if not self.send_to_supabase(payload):
                        print("× Adding to buffer for retry later")
                        self.buffer.append(payload)
                        print(f"Buffer size: {len(self.buffer)} readings")
                    else:
                        print("✓ Data successfully sent to Supabase")
                        
                    # Process buffer
                    if self.buffer:
                        print(f"Attempting to send {len(self.buffer)} buffered readings...")
                        successful_sends = []
                        for reading in self.buffer:
                            if self.send_to_supabase(reading):
                                successful_sends.append(reading)
                                print(f"✓ Buffered reading sent successfully")
                        
                        self.buffer = [r for r in self.buffer if r not in successful_sends]
                        print(f"Buffer size after retry: {len(self.buffer)} readings")
                        
                    time.sleep(300)  # 5 minute delay between readings
                        
                except ValueError as e:
                    print(f"× Error parsing data: {str(e)}")
                except Exception as e:
                    print(f"× Unexpected error: {str(e)}")
                    time.sleep(5)  # Short delay before retry on error
                    
        except serial.SerialException as e:
            print(f"× Error with serial connection: {str(e)}")
        except Exception as e:
            print(f"× Critical error: {str(e)}")
        finally:
            if serial_connection:
                try:
                    serial_connection.close()
                    print("Serial connection closed")
                except Exception as e:
                    print(f"× Error closing serial connection: {str(e)}")

if __name__ == "__main__":
    collector = SensorDataCollector()
    collector.run()