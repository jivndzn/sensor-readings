import serial.tools.list_ports

ports = serial.tools.list_ports.comports()
for port in ports:
    print(f"Found: {port.device} - {port.description}")
    