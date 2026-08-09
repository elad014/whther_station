
#include <WiFi.h>
#include <esp_now.h>

#include <Wire.h>
#include <TinyGPS++.h>
#include <Adafruit_BMP085.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_QMC5883P.h>


// =====================================================
// PIN DEFINITIONS
// =====================================================

#define SDA_PIN 21
#define SCL_PIN 22

#define GPS_RX 16
#define GPS_TX 17


// =====================================================
// ESP-NOW RECEIVER MAC
// =====================================================

uint8_t receiverMAC[] = {
  0xA4,
  0xCF,
  0x12,
  0xC6,
  0x8A,
  0xE3
};


// =====================================================
// SENSOR OBJECTS
// =====================================================

TinyGPSPlus gps;

HardwareSerial GPSserial(2);

Adafruit_BMP085 bmp;

Adafruit_MPU6050 mpu;

Adafruit_QMC5883P qmc;


// =====================================================
// SENSOR STATUS
// =====================================================

bool bmpOK = false;
bool mpuOK = false;
bool qmcOK = false;


// =====================================================
// MAIN ESP-NOW PACKET
//
// MUST MATCH THE ESP8266 RECEIVER
// =====================================================

struct MainSensorPacket {

  uint8_t packetType;
  uint8_t sensorID;


  // -------------------------
  // GPS NEO-8M
  // -------------------------

  float latitude;
  float longitude;
  float gpsAltitude;

  uint8_t satellites;

  float hdop;

  uint8_t hour;
  uint8_t minute;
  uint8_t second;

  uint8_t day;
  uint8_t month;
  uint16_t year;


  // -------------------------
  // BMP180
  // -------------------------

  float bmpTemperature;
  float pressure;
  float bmpAltitude;


  // -------------------------
  // MPU6050
  // -------------------------

  float accelX;
  float accelY;
  float accelZ;

  float gyroX;
  float gyroY;
  float gyroZ;

  float mpuTemperature;


  // -------------------------
  // HP5883 / QMC5883P
  // -------------------------

  int16_t magX;
  int16_t magY;
  int16_t magZ;

  float gaussX;
  float gaussY;
  float gaussZ;

  float heading;

  char direction[16];
};


// =====================================================
// PACKET
// =====================================================

MainSensorPacket packet;


// =====================================================
// SEND STATUS
// =====================================================

volatile bool sendFinished = false;
volatile bool sendSuccess = false;


// =====================================================
// ESP-NOW SEND CALLBACK
//
// ESP32 Arduino Core 3.x
// =====================================================

void onDataSent(
  const wifi_tx_info_t *info,
  esp_now_send_status_t status
) {

  sendFinished = true;

  if (status == ESP_NOW_SEND_SUCCESS) {
    sendSuccess = true;
  } else {
    sendSuccess = false;
  }
}


// =====================================================
// SETUP
// =====================================================

void setup() {

  Serial.begin(115200);

  delay(1000);


  Serial.println();
  Serial.println();
  Serial.println("================================");
  Serial.println("ESP32 SENSOR SYSTEM");
  Serial.println("================================");


  // ===================================================
  // I2C
  // ===================================================

  Wire.begin(
    SDA_PIN,
    SCL_PIN
  );


  // ===================================================
  // BMP180
  // ===================================================

  Serial.println();
  Serial.println("Starting BMP180...");

  if (bmp.begin()) {

    bmpOK = true;

    Serial.println("BMP180: OK");

  } else {

    bmpOK = false;

    Serial.println("BMP180: NOT FOUND");
  }


  // ===================================================
  // MPU6050
  // ===================================================

  Serial.println();
  Serial.println("Starting MPU6050...");

  if (mpu.begin()) {

    mpuOK = true;

    Serial.println("MPU6050: OK");


    mpu.setAccelerometerRange(
      MPU6050_RANGE_8_G
    );

    mpu.setGyroRange(
      MPU6050_RANGE_500_DEG
    );

    mpu.setFilterBandwidth(
      MPU6050_BAND_21_HZ
    );

  } else {

    mpuOK = false;

    Serial.println("MPU6050: NOT FOUND");
  }


  // ===================================================
  // QMC5883P
  // ===================================================

  Serial.println();
  Serial.println("Starting QMC5883P...");

  if (qmc.begin()) {

    qmcOK = true;

    Serial.println("QMC5883P: OK");


    qmc.setMode(
      QMC5883P_MODE_CONTINUOUS
    );

    qmc.setODR(
      QMC5883P_ODR_50HZ
    );

    qmc.setOSR(
      QMC5883P_OSR_4
    );

    qmc.setDSR(
      QMC5883P_DSR_2
    );

    qmc.setRange(
      QMC5883P_RANGE_8G
    );

    qmc.setSetResetMode(
      QMC5883P_SETRESET_ON
    );

  } else {

    qmcOK = false;

    Serial.println("QMC5883P: NOT FOUND");
  }


  // ===================================================
  // GPS
  // ===================================================

  Serial.println();
  Serial.println("Starting GPS...");

  GPSserial.begin(
    9600,
    SERIAL_8N1,
    GPS_RX,
    GPS_TX
  );

  Serial.println("GPS: OK");


  // ===================================================
  // WIFI
  // ===================================================

  Serial.println();
  Serial.println("Starting WiFi...");

  WiFi.mode(WIFI_STA);

  WiFi.disconnect();

  delay(100);

  Serial.print("ESP32 MAC: ");
  Serial.println(
    WiFi.macAddress()
  );


  // ===================================================
  // ESP-NOW
  // ===================================================

  Serial.println();
  Serial.println("Starting ESP-NOW...");

  if (
    esp_now_init() != ESP_OK
  ) {

    Serial.println(
      "ESP-NOW INIT FAILED!"
    );

    while (true) {
      delay(1000);
    }
  }


  esp_now_register_send_cb(
    onDataSent
  );


  // ===================================================
  // ADD ESP8266 RECEIVER
  // ===================================================

  esp_now_peer_info_t peerInfo = {};

  memcpy(
    peerInfo.peer_addr,
    receiverMAC,
    6
  );

  peerInfo.channel = 0;

  peerInfo.encrypt = false;


  if (
    esp_now_add_peer(&peerInfo)
    != ESP_OK
  ) {

    Serial.println(
      "FAILED TO ADD RECEIVER!"
    );

  } else {

    Serial.println(
      "ESP8266 RECEIVER ADDED"
    );
  }


  // ===================================================
  // PACKET IDENTIFICATION
  // ===================================================

  memset(
    &packet,
    0,
    sizeof(packet)
  );

  packet.packetType = 2;

  packet.sensorID = 4;


  Serial.println();
  Serial.println("================================");
  Serial.println("SYSTEM READY");
  Serial.println("================================");
}


// =====================================================
// READ GPS
// =====================================================

void readGPS() {

  while (
    GPSserial.available()
  ) {

    gps.encode(
      GPSserial.read()
    );
  }
}


// =====================================================
// FILL GPS DATA
// =====================================================

void fillGPSData() {

  // -------------------------
  // Position
  // -------------------------

  if (gps.location.isValid()) {

    packet.latitude =
      gps.location.lat();

    packet.longitude =
      gps.location.lng();

  } else {

    packet.latitude = 0.0;

    packet.longitude = 0.0;
  }


  // -------------------------
  // Altitude
  // -------------------------

  if (gps.altitude.isValid()) {

    packet.gpsAltitude =
      gps.altitude.meters();

  } else {

    packet.gpsAltitude = 0.0;
  }


  // -------------------------
  // Satellites
  // -------------------------

  if (gps.satellites.isValid()) {

    packet.satellites =
      gps.satellites.value();

  } else {

    packet.satellites = 0;
  }


  // -------------------------
  // HDOP
  // -------------------------

  if (gps.hdop.isValid()) {

    packet.hdop =
      gps.hdop.hdop();

  } else {

    packet.hdop = 0.0;
  }


  // -------------------------
  // Time
  // -------------------------

  if (gps.time.isValid()) {

    packet.hour =
      gps.time.hour();

    packet.minute =
      gps.time.minute();

    packet.second =
      gps.time.second();

  } else {

    packet.hour = 0;
    packet.minute = 0;
    packet.second = 0;
  }


  // -------------------------
  // Date
  // -------------------------

  if (gps.date.isValid()) {

    packet.day =
      gps.date.day();

    packet.month =
      gps.date.month();

    packet.year =
      gps.date.year();

  } else {

    packet.day = 0;
    packet.month = 0;
    packet.year = 0;
  }
}


// =====================================================
// FILL BMP180
// =====================================================

void fillBMPData() {

  if (!bmpOK) {

    packet.bmpTemperature = 0.0;
    packet.pressure = 0.0;
    packet.bmpAltitude = 0.0;

    return;
  }


  packet.bmpTemperature =
    bmp.readTemperature();


  packet.pressure =
    bmp.readPressure() / 100.0;


  packet.bmpAltitude =
    bmp.readAltitude();
}


// =====================================================
// FILL MPU6050
// =====================================================

void fillMPUData() {

  if (!mpuOK) {

    packet.accelX = 0.0;
    packet.accelY = 0.0;
    packet.accelZ = 0.0;

    packet.gyroX = 0.0;
    packet.gyroY = 0.0;
    packet.gyroZ = 0.0;

    packet.mpuTemperature = 0.0;

    return;
  }


  sensors_event_t accel;
  sensors_event_t gyro;
  sensors_event_t temp;


  mpu.getEvent(
    &accel,
    &gyro,
    &temp
  );


  packet.accelX =
    accel.acceleration.x;

  packet.accelY =
    accel.acceleration.y;

  packet.accelZ =
    accel.acceleration.z;


  packet.gyroX =
    gyro.gyro.x;

  packet.gyroY =
    gyro.gyro.y;

  packet.gyroZ =
    gyro.gyro.z;


  packet.mpuTemperature =
    temp.temperature;
}


// =====================================================
// GET DIRECTION FROM HEADING
// =====================================================

void getDirection(
  float heading,
  char *direction
) {

  if (
    heading >= 337.5 ||
    heading < 22.5
  ) {

    strcpy(
      direction,
      "NORTH"
    );

  } else if (
    heading < 67.5
  ) {

    strcpy(
      direction,
      "NORTHEAST"
    );

  } else if (
    heading < 112.5
  ) {

    strcpy(
      direction,
      "EAST"
    );

  } else if (
    heading < 157.5
  ) {

    strcpy(
      direction,
      "SOUTHEAST"
    );

  } else if (
    heading < 202.5
  ) {

    strcpy(
      direction,
      "SOUTH"
    );

  } else if (
    heading < 247.5
  ) {

    strcpy(
      direction,
      "SOUTHWEST"
    );

  } else if (
    heading < 292.5
  ) {

    strcpy(
      direction,
      "WEST"
    );

  } else {

    strcpy(
      direction,
      "NORTHWEST"
    );
  }
}


// =====================================================
// FILL QMC5883P
// =====================================================

void fillQMCData() {

  if (!qmcOK) {

    packet.magX = 0;
    packet.magY = 0;
    packet.magZ = 0;

    packet.gaussX = 0.0;
    packet.gaussY = 0.0;
    packet.gaussZ = 0.0;

    packet.heading = 0.0;

    strcpy(
      packet.direction,
      "NO DATA"
    );

    return;
  }


  if (!qmc.isDataReady()) {

    return;
  }


  int16_t x;
  int16_t y;
  int16_t z;

  float gx;
  float gy;
  float gz;


  // -------------------------
  // Raw magnetic
  // -------------------------

  if (
    qmc.getRawMagnetic(
      &x,
      &y,
      &z
    )
  ) {

    packet.magX = x;
    packet.magY = y;
    packet.magZ = z;
  }


  // -------------------------
  // Gauss
  // -------------------------

  if (
    qmc.getGaussField(
      &gx,
      &gy,
      &gz
    )
  ) {

    packet.gaussX = gx;
    packet.gaussY = gy;
    packet.gaussZ = gz;


    // -----------------------
    // Heading
    // -----------------------

    float heading =
      atan2(
        gy,
        gx
      );


    heading =
      heading * 180.0 / PI;


    if (heading < 0) {
      heading += 360.0;
    }


    packet.heading =
      heading;


    getDirection(
      heading,
      packet.direction
    );
  }


  // -------------------------
  // Overflow warning
  // -------------------------

  if (qmc.isOverflow()) {

    Serial.println(
      "WARNING: MAGNETIC OVERFLOW"
    );
  }
}


// =====================================================
// PRINT DATA BEFORE SEND
// =====================================================

void printPacket() {

  Serial.println();
  Serial.println("================================");
  Serial.println("DATA TO ESP8266");
  Serial.println("================================");


  // GPS

  Serial.println();
  Serial.println("--- GPS NEO-8M ---");

  Serial.print("Latitude:   ");
  Serial.println(
    packet.latitude,
    6
  );

  Serial.print("Longitude:  ");
  Serial.println(
    packet.longitude,
    6
  );

  Serial.print("Altitude:   ");
  Serial.print(
    packet.gpsAltitude,
    2
  );
  Serial.println(" m");

  Serial.print("Satellites: ");
  Serial.println(
    packet.satellites
  );

  Serial.print("HDOP:       ");
  Serial.println(
    packet.hdop,
    2
  );

  Serial.printf(
    "UTC Time:   %02d:%02d:%02d\n",
    packet.hour,
    packet.minute,
    packet.second
  );

  Serial.printf(
    "UTC Date:   %02d/%02d/%04d\n",
    packet.day,
    packet.month,
    packet.year
  );


  // BMP

  Serial.println();
  Serial.println("--- BMP180 ---");

  Serial.print("Temperature: ");
  Serial.print(
    packet.bmpTemperature,
    2
  );
  Serial.println(" C");

  Serial.print("Pressure:    ");
  Serial.print(
    packet.pressure,
    2
  );
  Serial.println(" hPa");

  Serial.print("Altitude:    ");
  Serial.print(
    packet.bmpAltitude,
    2
  );
  Serial.println(" m");


  // MPU

  Serial.println();
  Serial.println("--- MPU6050 ---");

  Serial.print("Accel X: ");
  Serial.println(
    packet.accelX,
    2
  );

  Serial.print("Accel Y: ");
  Serial.println(
    packet.accelY,
    2
  );

  Serial.print("Accel Z: ");
  Serial.println(
    packet.accelZ,
    2
  );

  Serial.print("Gyro X:  ");
  Serial.println(
    packet.gyroX,
    2
  );

  Serial.print("Gyro Y:  ");
  Serial.println(
    packet.gyroY,
    2
  );

  Serial.print("Gyro Z:  ");
  Serial.println(
    packet.gyroZ,
    2
  );

  Serial.print("MPU Temp: ");
  Serial.print(
    packet.mpuTemperature,
    2
  );
  Serial.println(" C");


  // QMC

  Serial.println();
  Serial.println("--- HP5883 / QMC5883P ---");

  Serial.print("Mag X:   ");
  Serial.println(
    packet.magX
  );

  Serial.print("Mag Y:   ");
  Serial.println(
    packet.magY
  );

  Serial.print("Mag Z:   ");
  Serial.println(
    packet.magZ
  );

  Serial.print("Gauss X: ");
  Serial.println(
    packet.gaussX,
    3
  );

  Serial.print("Gauss Y: ");
  Serial.println(
    packet.gaussY,
    3
  );

  Serial.print("Gauss Z: ");
  Serial.println(
    packet.gaussZ,
    3
  );

  Serial.print("Heading: ");
  Serial.print(
    packet.heading,
    1
  );
  Serial.println(" deg");

  Serial.print("Direction: ");
  Serial.println(
    packet.direction
  );
}


// =====================================================
// SEND PACKET
// =====================================================

void sendPacket() {

  sendFinished = false;
  sendSuccess = false;


  esp_err_t result =
    esp_now_send(
      receiverMAC,
      (uint8_t *)&packet,
      sizeof(packet)
    );


  Serial.println();
  Serial.println("--------------------------------");
  Serial.println("ESP-NOW SEND");
  Serial.println("--------------------------------");


  if (result != ESP_OK) {

    Serial.print(
      "Send start failed. Error: "
    );

    Serial.println(
      result
    );

    return;
  }


  // Wait briefly for callback

  unsigned long start =
    millis();


  while (
    !sendFinished &&
    millis() - start < 500
  ) {

    delay(1);
  }


  if (sendFinished) {

    if (sendSuccess) {

      Serial.println(
        "STATUS: SUCCESS"
      );

    } else {

      Serial.println(
        "STATUS: FAILED"
      );
    }

  } else {

    Serial.println(
      "STATUS: NO CALLBACK"
    );
  }


  Serial.print(
    "Packet size: "
  );

  Serial.print(
    sizeof(packet)
  );

  Serial.println(
    " bytes"
  );
}


// =====================================================
// LOOP
// =====================================================

void loop() {

  // ---------------------------------------------------
  // GPS MUST BE READ CONTINUOUSLY
  // ---------------------------------------------------

  readGPS();


  // ---------------------------------------------------
  // SEND EVERY 2 SECONDS
  // ---------------------------------------------------

  static unsigned long lastSend = 0;


  if (
    millis() - lastSend >= 2000
  ) {

    lastSend = millis();


    // Clear packet

    memset(
      &packet,
      0,
      sizeof(packet)
    );


    // Identification

    packet.packetType = 2;

    packet.sensorID = 4;


    // Read all sensors

    fillGPSData();

    fillBMPData();

    fillMPUData();

    fillQMCData();


    // Show locally

    printPacket();


    // Send to ESP8266

    sendPacket();
  }


  delay(2);
}
