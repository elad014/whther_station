#include <ESP8266WiFi.h>
#include <espnow.h>
#include <DHT.h>

// =====================================================
// DHT11
// =====================================================

#define DHT_PIN 2          // D1 = GPIO5
#define DHT_TYPE DHT22


DHT dht(DHT_PIN, DHT_TYPE);


// =====================================================
// ESP-NOW
// =====================================================

// MAC address of ESP8266 central receiver
uint8_t receiverMAC[] = {
  0xA4,
  0xCF,
  0x12,
  0xC6,
  0x8A,
  0xE3
};


// =====================================================
// SENSOR ID
// =====================================================

#define PACKET_DHT  1
#define SENSOR_ID   3


// =====================================================
// DATA STRUCTURE
//
// MUST MATCH THE ESP8266 RECEIVER
// =====================================================

struct DHTPacket {

  uint8_t packetType;
  uint8_t sensorID;

  float temperature;
  float humidity;
};


DHTPacket packet;


// =====================================================
// SEND CALLBACK
// =====================================================

void onDataSent(
  uint8_t *mac,
  uint8_t status
) {

  Serial.print("ESP-NOW Send: ");

  if (status == 0) {
    Serial.println("SUCCESS");
  } else {
    Serial.println("FAILED");
  }
}


// =====================================================
// SETUP
// =====================================================

void setup() {

  Serial.begin(115200);

  delay(1000);


  Serial.println();
  Serial.println("================================");
  Serial.println("ESP8266 DHT11 ESP-NOW TRANSMITTER");
  Serial.println("================================");


  // ===================================================
  // DHT
  // ===================================================

  Serial.println();
  Serial.println("Starting DHT11...");

  dht.begin();

  Serial.println("DHT11: OK");


  // ===================================================
  // WIFI
  // ===================================================

  WiFi.mode(WIFI_STA);

  WiFi.disconnect();

  delay(100);


  Serial.print("ESP8266 MAC: ");
  Serial.println(
    WiFi.macAddress()
  );


  // ===================================================
  // ESP-NOW
  // ===================================================

  Serial.println();
  Serial.println("Starting ESP-NOW...");


  if (
    esp_now_init() != 0
  ) {

    Serial.println(
      "ESP-NOW INIT FAILED!"
    );

    while (true) {
      delay(1000);
    }
  }


  // ESP8266 role

  esp_now_set_self_role(
    ESP_NOW_ROLE_COMBO
  );


  // Register send callback

  esp_now_register_send_cb(
    onDataSent
  );


  // ===================================================
  // REGISTER RECEIVER
  // ===================================================

  Serial.println(
    "Adding central receiver..."
  );


  if (
    esp_now_add_peer(
      receiverMAC,
      ESP_NOW_ROLE_COMBO,
      0,
      NULL,
      0
    ) != 0
  ) {

    Serial.println(
      "FAILED TO ADD RECEIVER!"
    );

  } else {

    Serial.println(
      "CENTRAL RECEIVER ADDED"
    );
  }


  // ===================================================
  // PACKET IDENTIFICATION
  // ===================================================

  packet.packetType = PACKET_DHT;

  packet.sensorID = SENSOR_ID;


  Serial.println();
  Serial.println("================================");
  Serial.println("SYSTEM READY");
  Serial.println("================================");

  Serial.println();
  Serial.print("Sensor ID: ");
  Serial.println(SENSOR_ID);

  Serial.println("Sending every 2 seconds...");
}


// =====================================================
// LOOP
// =====================================================

void loop() {

  static unsigned long lastRead = 0;


  if (
    millis() - lastRead >= 2000
  ) {

    lastRead = millis();


    // =================================================
    // READ DHT11
    // =================================================

    float humidity =
      dht.readHumidity();

    float temperature =
      dht.readTemperature();


    // =================================================
    // CHECK DATA
    // =================================================

    if (
      isnan(humidity) ||
      isnan(temperature)
    ) {

      Serial.println();
      Serial.println(
        "DHT11: READ ERROR"
      );

      return;
    }


    // =================================================
    // FILL PACKET
    // =================================================

    packet.packetType =
      PACKET_DHT;

    packet.sensorID =
      SENSOR_ID;

    packet.temperature =
      temperature;

    packet.humidity =
      humidity;


    // =================================================
    // PRINT
    // =================================================

    Serial.println();
    Serial.println("--------------------------------");
    Serial.println("DHT11 DATA");
    Serial.println("--------------------------------");

    Serial.print("Temperature: ");
    Serial.print(
      packet.temperature,
      2
    );
    Serial.println(" C");

    Serial.print("Humidity:    ");
    Serial.print(
      packet.humidity,
      2
    );
    Serial.println(" %");


    // =================================================
    // SEND
    // =================================================

    Serial.println();
    Serial.println(
      "Sending via ESP-NOW..."
    );


    uint8_t result =
      esp_now_send(
        receiverMAC,
        (uint8_t *)&packet,
        sizeof(packet)
      );


    if (result == 0) {

      Serial.println(
        "Packet accepted for sending"
      );

    } else {

      Serial.print(
        "Send error: "
      );

      Serial.println(result);
    }
  }


  delay(10);
}