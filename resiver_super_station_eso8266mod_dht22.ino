#include <ESP8266WiFi.h>
#include <espnow.h>
#include <DHT.h>

// =====================================================
// LOCAL DHT11
// =====================================================

#define DHT_PIN 5       // D2 = GPIO4
#define DHT_TYPE DHT22

DHT dht(DHT_PIN, DHT_TYPE);


// =====================================================
// ESP-NOW IDs
// =====================================================

#define SENSOR_DHT1  1
#define SENSOR_DHT2  2
#define SENSOR_DHT3  3
#define SENSOR_MAIN  4
#define SENSOR_DHT4  5  // <--- התווסף חיישן 4 (קיבל ID 5 כי Main הוא 4)

#define PACKET_DHT   1
#define PACKET_MAIN  2


// =====================================================
// TIMEOUT
// =====================================================

#define SENSOR_TIMEOUT 10000UL


// =====================================================
// DHT PACKET
// =====================================================

struct DHTPacket {
  uint8_t packetType;
  uint8_t sensorID;
  float temperature;
  float humidity;
};


// =====================================================
// MAIN SENSOR PACKET
//
// ESP32 #4 sends:
// GPS + BMP180 + MPU6050 + HP5883/QMC5883P
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
// RECEIVED DATA
// =====================================================

DHTPacket dht1Data;
DHTPacket dht2Data;
DHTPacket dht3Data;
DHTPacket dht4Data; // <--- משתנה למידע של חיישן 4

MainSensorPacket mainData;


// =====================================================
// RECEIVE FLAGS
// =====================================================

bool dht1Received = false;
bool dht2Received = false;
bool dht3Received = false;
bool dht4Received = false; // <--- דגל קבלה לחיישן 4
bool mainReceived = false;


// =====================================================
// LAST RECEIVE TIME
// =====================================================

unsigned long dht1LastReceive = 0;
unsigned long dht2LastReceive = 0;
unsigned long dht3LastReceive = 0;
unsigned long dht4LastReceive = 0; // <--- זמן קבלה אחרון לחיישן 4
unsigned long mainLastReceive = 0;


// =====================================================
// LOCAL DHT
// =====================================================

float localTemperature = NAN;
float localHumidity = NAN;


// =====================================================
// ESP-NOW RECEIVE CALLBACK
// =====================================================

void onDataReceive(
  uint8_t *mac,
  uint8_t *data,
  uint8_t len
) {
  if (data == nullptr) {
    return;
  }

  // ===================================================
  // DHT PACKET
  // ===================================================
  if (len == sizeof(DHTPacket)) {
    DHTPacket packet;
    memcpy(&packet, data, sizeof(DHTPacket));

    if (packet.packetType != PACKET_DHT) {
      return;
    }

    if (packet.sensorID == SENSOR_DHT1) {
      memcpy(&dht1Data, &packet, sizeof(DHTPacket));
      dht1Received = true;
      dht1LastReceive = millis();
    }
    else if (packet.sensorID == SENSOR_DHT2) {
      memcpy(&dht2Data, &packet, sizeof(DHTPacket));
      dht2Received = true;
      dht2LastReceive = millis();
    }
    else if (packet.sensorID == SENSOR_DHT3) {
      memcpy(&dht3Data, &packet, sizeof(DHTPacket));
      dht3Received = true;
      dht3LastReceive = millis();
    }
    // <--- תוספת הטיפול בחיישן מספר 4
    else if (packet.sensorID == SENSOR_DHT4) {
      memcpy(&dht4Data, &packet, sizeof(DHTPacket));
      dht4Received = true;
      dht4LastReceive = millis();
    }

    return;
  }

  // ===================================================
  // MAIN SENSOR PACKET
  // ===================================================
  if (len == sizeof(MainSensorPacket)) {
    MainSensorPacket packet;
    memcpy(&packet, data, sizeof(MainSensorPacket));

    if (packet.packetType != PACKET_MAIN) {
      return;
    }

    if (packet.sensorID != SENSOR_MAIN) {
      return;
    }

    memcpy(&mainData, &packet, sizeof(MainSensorPacket));
    mainReceived = true;
    mainLastReceive = millis();

    return;
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
  Serial.println("==================================================");
  Serial.println("          ESP8266 CENTRAL RECEIVER");
  Serial.println("==================================================");

  // ===================================================
  // LOCAL DHT11
  // ===================================================
  Serial.println();
  Serial.println("Starting local DHT11...");
  dht.begin();
  Serial.println("Local DHT11: OK");

  // ===================================================
  // WIFI
  // ===================================================
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);

  Serial.println();
  Serial.println("WiFi Mode: STA");
  Serial.print("Receiver MAC: ");
  Serial.println(WiFi.macAddress());

  // ===================================================
  // ESP-NOW
  // ===================================================
  Serial.println();
  Serial.println("Starting ESP-NOW...");

  if (esp_now_init() != 0) {
    Serial.println("ESP-NOW INIT FAILED!");
    while (true) {
      delay(1000);
    }
  }

  esp_now_set_self_role(ESP_NOW_ROLE_COMBO);
  esp_now_register_recv_cb(onDataReceive);

  Serial.println("ESP-NOW: OK");

  // ===================================================
  // READY
  // ===================================================
  Serial.println();
  Serial.println("==================================================");
  Serial.println("SYSTEM READY");
  Serial.println("==================================================");

  Serial.println();
  Serial.println("Waiting for:");
  Serial.println("ESP-NOW DHT11 #1");
  Serial.println("ESP-NOW DHT11 #2");
  Serial.println("ESP-NOW DHT11 #3");
  Serial.println("ESP-NOW DHT11 #4"); // <--- הדפסה של חיישן 4 
  Serial.println("ESP-NOW GPS/BMP180/MPU6050/HP5883");
  Serial.println();
}


// =====================================================
// READ LOCAL DHT11
// =====================================================

void readLocalDHT() {
  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();

  if (!isnan(temperature)) {
    localTemperature = temperature;
  }
  if (!isnan(humidity)) {
    localHumidity = humidity;
  }
}


// =====================================================
// PRINT LOCAL DHT
// =====================================================

void printLocalDHT() {
  Serial.println();
  Serial.println("--- LOCAL DHT11 ---");

  Serial.print("Temperature: ");
  if (isnan(localTemperature)) {
    Serial.println("NO DATA");
  } else {
    Serial.print(localTemperature, 2);
    Serial.println(" C");
  }

  Serial.print("Humidity:    ");
  if (isnan(localHumidity)) {
    Serial.println("NO DATA");
  } else {
    Serial.print(localHumidity, 2);
    Serial.println(" %");
  }
}


// =====================================================
// CHECK DHT STATUS
// =====================================================

bool isDHTOnline(
  bool received,
  unsigned long lastReceive
) {
  if (!received) {
    return false;
  }
  if (millis() - lastReceive > SENSOR_TIMEOUT) {
    return false;
  }
  return true;
}


// =====================================================
// PRINT ESP-NOW DHT
// =====================================================

void printDHTSensor(
  const char *name,
  DHTPacket &data,
  bool received,
  unsigned long lastReceive
) {
  Serial.println();
  Serial.print("--- ");
  Serial.print(name);
  Serial.println(" ---");

  if (!isDHTOnline(received, lastReceive)) {
    Serial.println("Status: OFFLINE");
    return;
  }

  Serial.println("Status: ONLINE");

  Serial.print("Temperature: ");
  Serial.print(data.temperature, 2);
  Serial.println(" C");

  Serial.print("Humidity:    ");
  Serial.print(data.humidity, 2);
  Serial.println(" %");

  Serial.print("Last packet: ");
  Serial.print((millis() - lastReceive) / 1000);
  Serial.println(" sec ago");
}


// =====================================================
// PRINT MAIN SENSOR
// =====================================================

void printMainSensor() {
  Serial.println();
  Serial.println("--- ESP-NOW MAIN SENSOR ---");

  if (!mainReceived || millis() - mainLastReceive > SENSOR_TIMEOUT) {
    Serial.println("Status: OFFLINE");
    return;
  }

  Serial.println("Status: ONLINE");

  // ===================================================
  // GPS
  // ===================================================
  Serial.println();
  Serial.println("--- GPS NEO-8M ---");
  Serial.print("Latitude:   ");
  Serial.println(mainData.latitude, 6);
  Serial.print("Longitude:  ");
  Serial.println(mainData.longitude, 6);
  Serial.print("Altitude:   ");
  Serial.print(mainData.gpsAltitude, 2);
  Serial.println(" m");
  Serial.print("Satellites: ");
  Serial.println(mainData.satellites);
  Serial.print("HDOP:       ");
  Serial.println(mainData.hdop, 2);
  
  Serial.print("UTC Time:   ");
  if (mainData.hour < 10) Serial.print("0");
  Serial.print(mainData.hour);
  Serial.print(":");
  if (mainData.minute < 10) Serial.print("0");
  Serial.print(mainData.minute);
  Serial.print(":");
  if (mainData.second < 10) Serial.print("0");
  Serial.println(mainData.second);

  Serial.print("UTC Date:   ");
  if (mainData.day < 10) Serial.print("0");
  Serial.print(mainData.day);
  Serial.print("/");
  if (mainData.month < 10) Serial.print("0");
  Serial.print(mainData.month);
  Serial.print("/");
  Serial.println(mainData.year);

  // ===================================================
  // BMP180
  // ===================================================
  Serial.println();
  Serial.println("--- BMP180 ---");
  Serial.print("Temperature: ");
  Serial.print(mainData.bmpTemperature, 2);
  Serial.println(" C");
  Serial.print("Pressure:    ");
  Serial.print(mainData.pressure, 2);
  Serial.println(" hPa");
  Serial.print("Altitude:    ");
  Serial.print(mainData.bmpAltitude, 2);
  Serial.println(" m");

  // ===================================================
  // MPU6050
  // ===================================================
  Serial.println();
  Serial.println("--- MPU6050 ---");
  Serial.print("Accel X: ");
  Serial.print(mainData.accelX, 2);
  Serial.println(" m/s2");
  Serial.print("Accel Y: ");
  Serial.print(mainData.accelY, 2);
  Serial.println(" m/s2");
  Serial.print("Accel Z: ");
  Serial.print(mainData.accelZ, 2);
  Serial.println(" m/s2");
  Serial.print("Gyro X:  ");
  Serial.print(mainData.gyroX, 2);
  Serial.println(" rad/s");
  Serial.print("Gyro Y:  ");
  Serial.print(mainData.gyroY, 2);
  Serial.println(" rad/s");
  Serial.print("Gyro Z:  ");
  Serial.print(mainData.gyroZ, 2);
  Serial.println(" rad/s");
  Serial.print("MPU Temp: ");
  Serial.print(mainData.mpuTemperature, 2);
  Serial.println(" C");

  // ===================================================
  // HP5883 / QMC5883P
  // ===================================================
  Serial.println();
  Serial.println("--- HP5883 / QMC5883P ---");
  Serial.print("Mag X:   ");
  Serial.println(mainData.magX);
  Serial.print("Mag Y:   ");
  Serial.println(mainData.magY);
  Serial.print("Mag Z:   ");
  Serial.println(mainData.magZ);
  Serial.print("Gauss X: ");
  Serial.println(mainData.gaussX, 3);
  Serial.print("Gauss Y: ");
  Serial.println(mainData.gaussY, 3);
  Serial.print("Gauss Z: ");
  Serial.println(mainData.gaussZ, 3);
  Serial.print("Heading: ");
  Serial.print(mainData.heading, 1);
  Serial.println(" deg");
  Serial.print("Direction: ");
  Serial.println(mainData.direction);

  Serial.print("Last packet: ");
  Serial.print((millis() - mainLastReceive) / 1000);
  Serial.println(" sec ago");
}


// =====================================================
// LOOP
// =====================================================

void loop() {
  // ---------------------------------------------------
  // Local DHT11
  // ---------------------------------------------------
  static unsigned long lastDHTRead = 0;
  if (millis() - lastDHTRead >= 2000) {
    lastDHTRead = millis();
    readLocalDHT();
  }

  // ---------------------------------------------------
  // Serial output
  // ---------------------------------------------------
  static unsigned long lastPrint = 0;
  if (millis() - lastPrint >= 3000) {
    lastPrint = millis();

    Serial.println();
    Serial.println();
    Serial.println("==================================================");
    Serial.println("            CENTRAL SENSOR DATA");
    Serial.println("==================================================");

    // Local DHT
    printLocalDHT();

    // ESP-NOW DHT #1
    printDHTSensor(
      "ESP-NOW DHT11 #1",
      dht1Data,
      dht1Received,
      dht1LastReceive
    );

    // ESP-NOW DHT #2
    printDHTSensor(
      "ESP-NOW DHT11 #2",
      dht2Data,
      dht2Received,
      dht2LastReceive
    );

    // ESP-NOW DHT #3
    printDHTSensor(
      "ESP-NOW DHT11 #3",
      dht3Data,
      dht3Received,
      dht3LastReceive
    );

    // ESP-NOW DHT #4 <--- תוספת ההדפסה לחיישן 4
    printDHTSensor(
      "ESP-NOW DHT11 #4",
      dht4Data,
      dht4Received,
      dht4LastReceive
    );

    // ESP-NOW main sensor
    printMainSensor();

    Serial.println();
    Serial.println("==================================================");
  }

  delay(10);
}