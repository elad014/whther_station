const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE HTML><html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    html {
     font-family: Arial;
     display: inline-block;
     margin: 0px auto;
     text-align: center;
    }
    h2 { font-size: 3.0rem; }
    p { font-size: 3.0rem; }
    .units { font-size: 1.2rem; }
    .dht-labels{
      font-size: 1.5rem;
      vertical-align:middle;
      padding-bottom: 15px;
    }
  </style>
</head>
<body>
  <h2>outdoor sensour</h2>
  <p>
    <i class="fas fa-thermometer-half" style="color:#059e8a;"></i> 
    <span class="dht-labels">Temperature</span> 
    <span id="temperature">%TEMPERATURE%</span>
    <sup class="units">&deg;C</sup>
  </p>
  <p>
    <i class="fas fa-tint" style="color:#00add6;"></i> 
    <span class="dht-labels">Humidity</span>
    <span id="humidity">%HUMIDITY%</span>
    <sup class="units">%</sup>
  </p>
</body>
<script>
setInterval(function ( ) {
  var xhttp = new XMLHttpRequest();
  xhttp.onreadystatechange = function() {
    if (this.readyState == 4 && this.status == 200) {
      document.getElementById("temperature").innerHTML = this.responseText;
    }
  };
  xhttp.open("GET", "/temperature", true);
  xhttp.send();
}, 10000 ) ;

setInterval(function ( ) {
  var xhttp = new XMLHttpRequest();
  xhttp.onreadystatechange = function() {
    if (this.readyState == 4 && this.status == 200) {
      document.getElementById("humidity").innerHTML = this.responseText;
    }
  };
  xhttp.open("GET", "/humidity", true);
  xhttp.send();
}, 10000 ) ;
</script>
</html>)rawliteral";



#include <ESP8266WiFi.h>  // for esp 8266
#include <WiFiClient.h>   // for esp 8266
//#include <WiFi.h> //for esp 32
#include <WiFiUdp.h>
#include "ESPAsyncWebServer.h"
#include <Adafruit_Sensor.h>
#include <DHT.h>
#include <stdlib.h>

#define DHTTYPE DHT22
#define DHTPIN 5  
const char *ssid = "";
const char *password = "";

WiFiUDP Udp;
DHT dht(DHTPIN, DHTTYPE);

IPAddress local_IP(10, 0, 0, 101);  
IPAddress subnet(255, 255, 0, 0);
IPAddress gateway(10, 0, 0, 138);
IPAddress serverip(10, 0, 0, 100);  

AsyncWebServer server(80);

String local_temperature = "-272";
String local_humidity = "0";
String portid = "101";
unsigned int serverPort = 200;


void setup() {
  Serial.begin(115200);
  delay(100);
  pinMode(DHTPIN, INPUT);
  dht.begin();


  WiFi.mode(WIFI_STA);
  if (!WiFi.config(local_IP, gateway, subnet)) {
    Serial.println("Configuration Failed!");
  }
  WiFi.begin(ssid, password);

  Serial.println("\nConnecting to WiFi Network ..");
  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    delay(100);
  }

  Serial.println(WiFi.localIP());
  server.on("/", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/html", index_html);
  });
  server.on("/temperature", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/plain", String(local_temperature).c_str());
  });
  server.on("/humidity", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/plain", String(local_humidity).c_str());
  });

  Udp.begin(serverPort);
  server.begin();
}

void loop() {
  String packet = "";
  local_temperature = String(dht.readTemperature());
  local_humidity = String(dht.readHumidity());
  packet = portid;
  packet += ",";
  packet += local_temperature;
  packet += ",";
  packet += local_humidity;
  packet += ",";
  packet += portid;
  Serial.println(packet);
  Udp.beginPacket(serverip, serverPort);
  Udp.print(packet);
  Udp.endPacket();
  delay(60000);
  //Elad Natan
}
