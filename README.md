# Weather Station

A multi-node wireless weather station system built with ESP8266/ESP32 microcontrollers and a Raspberry Pi smart-home dashboard.

## System Architecture

```
                         ESP-NOW (2.4GHz)
 ┌──────────────┐         ┌──────────────┐
 │ DHT Sensor 1 │────┐    │ ESP32 Main   │
 │ (ESP8266)    │    │    │ BMP180       │
 └──────────────┘    │    │ MPU6050      │
 ┌──────────────┐    │    │ QMC5883P     │
 │ DHT Sensor 2 │────┼───▶│ NEO-8M GPS   │──┐
 │ (ESP8266)    │    │    └──────────────┘  │
 └──────────────┘    │                      │
 ┌──────────────┐    │                      │
 │ DHT Sensor 3 │────┤    ESP-NOW           │
 │ (ESP8266)    │    │                      │
 └──────────────┘    │    ┌──────────────┐  │
 ┌──────────────┐    └───▶│ Central RX   │◀─┘
 │ DHT Sensor 4 │────────▶│ (ESP8266)    │
 │ (ESP8266)    │         │ + DHT22      │
 └──────────────┘         └──────┬───────┘
                                 │ USB Serial
                          ┌──────▼───────┐
                          │ Raspberry Pi │
                          │ Pygame UI    │
                          └──────────────┘
```

## Hardware

| Node | MCU | Sensors | Role |
|------|-----|---------|------|
| Remote sensors (x4) | ESP8266 | DHT11/DHT22 | Transmit temperature + humidity via ESP-NOW |
| Main sensor | ESP-WROOM-32 | BMP180, MPU6050, QMC5883P, NEO-8M GPS | Transmit pressure, motion, compass, GPS via ESP-NOW |
| Central receiver | ESP8266 | DHT22 (local) | Collect all ESP-NOW packets, output frames over USB serial |
| Dashboard | Raspberry Pi | — | Read serial, render fullscreen smart-home UI |

## Sensors

- **DHT11/DHT22** — Temperature and humidity
- **BMP180** — Barometric pressure, temperature, altitude
- **MPU6050** — 6-axis accelerometer + gyroscope
- **QMC5883P** — 3-axis magnetometer, compass heading
- **NEO-8M** — GPS (lat/lon, altitude, satellites, UTC time)

## Software Components

### Firmware (Arduino)

| File | Target | Description |
|------|--------|-------------|
| `super_station_tx_esp8266mod_dht11.ino` | ESP8266 | DHT sensor transmitter node (ESP-NOW) |
| `super_station_tx_esp-wroom-32_bmp180_mpu6050_hp5883_neo-m8.ino` | ESP32 | Multi-sensor transmitter (GPS + pressure + motion + compass) |
| `resiver_super_station_eso8266mod_dht22.ino` | ESP8266 | Central receiver — aggregates all ESP-NOW packets, prints serial frames |

### Dashboard (`super_station_app.py`)

Python Pygame application designed for Raspberry Pi fullscreen display.

**Features:**
- Real-time temperature gauges per room (ring-style)
- Weather inference from humidity + pressure + sun altitude
- Live GPS map (OpenStreetMap tiles, cached)
- Solar tracking (sunrise, sunset, day length, sun relative to compass)
- Clock synced from GPS UTC
- Israeli holidays (Hebcal API)
- Custom background photo support (`~/super_station_bg.png`)
- Frosted-glass card UI with text outlines for readability
- Auto-detect USB serial port
- Demo mode for testing without hardware

**Dependencies:**
```
pygame
pyserial
Pillow
```

**Usage:**
```bash
# Auto-detect serial port, fullscreen
python super_station_app.py

# Specify port
python super_station_app.py --port /dev/ttyUSB0

# Windowed mode
python super_station_app.py --windowed

# Demo mode (replay from file)
python super_station_app.py --demo ~/serial_output.txt
```

## Communication Protocol

Nodes communicate via **ESP-NOW** (low-latency, connectionless, no WiFi router needed).

**Packet types:**
- `PACKET_DHT (1)` — 10 bytes: packetType, sensorID, temperature (float), humidity (float)
- `PACKET_MAIN (2)` — ~134 bytes: GPS + BMP180 + MPU6050 + QMC5883P data

Receiver prints structured serial frames every 3 seconds with timeout detection (10s = OFFLINE).

## V1.0 (Legacy)

The `whtherStationVer1.0/` folder contains an older WiFi-based version using UDP packets and a web dashboard hosted directly on the ESP8266 server node.

## Wiring

**ESP32 Main Sensor:**
- I2C: SDA=GPIO21, SCL=GPIO22 (BMP180, MPU6050, QMC5883P)
- GPS: RX=GPIO16, TX=GPIO17 (NEO-8M at 9600 baud)

**ESP8266 DHT Nodes:**
- DHT data pin: GPIO2 (D4)

**ESP8266 Central Receiver:**
- DHT22 data pin: GPIO5 (D1)
- USB serial to Raspberry Pi at 115200 baud
