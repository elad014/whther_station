const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE HTML><html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    html {
      font-family: Arial;
      display: inline-block;
      margin: 0px auto;
      text-align: center;
    }

    body {
      background-color: black;
    }

    .container {
      border: 4px solid white;
      display: grid;
      grid-template-areas:
        "top-left top-right"
        "bottom-left bottom-right";
      grid-template-rows: 50% 50%;
      grid-template-columns: 50% 50%;
      height: 100vh;
    }

    .sensor-box {
      background-color: white;
      padding: 20px;
      margin: 5px;
      border: 2px solid black;
      text-align: center;
      color: black;
    }

    .sensor-box h2 { font-size: 3.0rem; }
    .sensor-box p { font-size: 2.0rem; }
    .sensor-box .units { font-size: 2.5rem; }
    .sensor-box .dht-labels {
      font-size: 2.0rem;
      vertical-align: middle;
      padding-bottom: 15px;
    }

    .top-left { grid-area: top-left; }
    .top-right { grid-area: top-right; }
    .bottom-left { grid-area: bottom-left; }
    .bottom-right { grid-area: bottom-right; }
  </style>
</head>
<body>
  <div class="container">
    <div class="sensor-box top-right">
      <h2>Living Room</h2>
      <p>
        <i class="fas fa-thermometer-half" style="color:#059e8a;"></i>
        <span class="dht-labels">Temperature</span>
        <span id="living_room_temperature">-272</span>
        <sup class="units">&deg;C</sup>
      </p>
      <p>
        <i class="fas fa-tint" style="color:#00add6;"></i>
        <span class="dht-labels">Humidity</span>
        <span id="living_room_humidity">0</span>
        <sup class="units">%</sup>
      </p>
    </div>

    <div class="sensor-box bottom-left">
      <h2>Outdoor</h2>
      <p>
        <i class="fas fa-thermometer-half" style="color:#059e8a;"></i>
        <span class="dht-labels">Temperature</span>
        <span id="out_temperature">-272</span>
        <sup class="units">&deg;C</sup>
      </p>
      <p>
        <i class="fas fa-tint" style="color:#00add6;"></i>
        <span class="dht-labels">Humidity</span>
        <span id="out_humidity">0</span>
        <sup class="units">%</sup>
      </p>
    </div>

    <div class="sensor-box bottom-right">
      <h2>Bedroom</h2>
      <p>
        <i class="fas fa-thermometer-half" style="color:#059e8a;"></i>
        <span class="dht-labels">Temperature</span>
        <span id="bed_room_temperture">-272</span>
        <sup class="units">&deg;C</sup>
      </p>
      <p>
        <i class="fas fa-tint" style="color:#00add6;"></i>
        <span class="dht-labels">Humidity</span>
        <span id="bed_room_humidity">0</span>
        <sup class="units">%</sup>
      </p>
    </div>
    <div class="sensor-box top-left">
    <a class="weatherwidget-io" href="https://forecast7.com/en/31d7934d76/bnei-ayish/" data-label_1="BNEI AYISH" >BNEI AYISH</a>
<script>
!function(d,s,id){var js,fjs=d.getElementsByTagName(s)[0];if(!d.getElementById(id)){js=d.createElement(s);js.id=id;js.src='https://weatherwidget.io/js/widget.min.js';fjs.parentNode.insertBefore(js,fjs);}}(document,'script','weatherwidget-io-js');
</script>
  </div>
</body>
<script>
setInterval(function ( ) {
  var xhttp = new XMLHttpRequest();
  xhttp.onreadystatechange = function() {
    if (this.readyState == 4 && this.status == 200) {
      document.getElementById("living_room_temperature").innerHTML = this.responseText;
    }
  };
  xhttp.open("GET", "/living_room_temperature", true);
  xhttp.send();
}, 10000 ) ;
setInterval(function ( ) {
  var xhttp = new XMLHttpRequest();
  xhttp.onreadystatechange = function() {
    if (this.readyState == 4 && this.status == 200) {
      document.getElementById("living_room_humidity").innerHTML = this.responseText;
    }
  };
  xhttp.open("GET", "/living_room_humidity", true);
  xhttp.send();
}, 10000 ) ;



setInterval(function ( ) {
  var xhttp = new XMLHttpRequest();
  xhttp.onreadystatechange = function() {
    if (this.readyState == 4 && this.status == 200) {
      document.getElementById("out_temperature").innerHTML = this.responseText;
    }
  };
  xhttp.open("GET", "/out_temperature", true);
  xhttp.send();
}, 10000 ) ;
setInterval(function ( ) {
  var xhttp = new XMLHttpRequest();
  xhttp.onreadystatechange = function() {
    if (this.readyState == 4 && this.status == 200) {
      document.getElementById("out_humidity").innerHTML = this.responseText;
    }
  };
  xhttp.open("GET", "/out_humidity", true);
  xhttp.send();
}, 10000 ) ;


setInterval(function ( ) {
  var xhttp = new XMLHttpRequest();
  xhttp.onreadystatechange = function() {
    if (this.readyState == 4 && this.status == 200) {
      document.getElementById("bed_room_temperture").innerHTML = this.responseText;
    }
  };
  xhttp.open("GET", "/bed_room_temperture", true);
  xhttp.send();
}, 10000 ) ;
setInterval(function ( ) {
  var xhttp = new XMLHttpRequest();
  xhttp.onreadystatechange = function() {
    if (this.readyState == 4 && this.status == 200) {
      document.getElementById("bed_room_humidity").innerHTML = this.responseText;
    }
  };
  xhttp.open("GET", "/bed_room_humidity", true);
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

#define PACKET_DELAY_DELAY 600000  // 10 minutes
#define DHTTYPE DHT22
#define DHTPIN 5  
const char *ssid = "";
const char *password = "";
String room1_PORT = "101";  //outdoor
String room2_PORT = "102";  //indoor

WiFiUDP Udp;
DHT dht(DHTPIN, DHTTYPE);

IPAddress local_IP(10, 0, 0, 100);  // Static IP Address
IPAddress subnet(255, 255, 0, 0);
IPAddress gateway(10, 0, 0, 138);

AsyncWebServer server(80);


String local_temperature = "-272";
String local_humidity = "0";
String room1_temperature = "-272";
String room1_humidity = "0";
String room2_temperature = "-272";
String room2_humidity = "0";
unsigned int localUdpPort = 200;  //  port to listen on
char incomingPacket[255];         
unsigned long lastByteReceivedTimePort1 = 0;
unsigned long lastByteReceivedTimePort2 = 0;


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


  // Handle Web Server Events

  server.on("/", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/html", index_html);
  });
  server.on("/living_room_humidity", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/plain", String(local_humidity).c_str());
  });
  server.on("/living_room_temperature", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/plain", String(local_temperature).c_str());
  });
  server.on("/out_humidity", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/plain", String(room1_humidity).c_str());
  });
  server.on("/out_temperature", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/plain", String(room1_temperature).c_str());
  });
  server.on("/bed_room_humidity", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/plain", String(room2_humidity).c_str());
  });
  server.on("/bed_room_temperture", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send_P(200, "text/plain", String(room2_temperature).c_str());
  });

  Udp.begin(localUdpPort);

  server.begin();
}

void loop() {
  String str_port = "";
  String str_temp = "";
  String str_humidity = "";

  int packetSize = Udp.parsePacket();
  Udp.read(incomingPacket, 255);
  if (millis() - lastByteReceivedTimePort1 >= PACKET_DELAY_DELAY) {
    room1_temperature = "-1";
    room1_humidity = "-1";
  }
  if (millis() - lastByteReceivedTimePort2 >= PACKET_DELAY_DELAY) {
    room2_temperature = "-1";
    room2_humidity = "-1";
  }
  if (packetSize > 0) {
    //parse incoming adress
    str_port += incomingPacket[0];
    str_port += incomingPacket[1];
    str_port += incomingPacket[2];
    //parse temperture
    str_temp += incomingPacket[4];
    str_temp += incomingPacket[5];
    str_temp += incomingPacket[6];
    str_temp += incomingPacket[7];
    str_temp += incomingPacket[8];
    //parse humidity
    str_humidity += incomingPacket[10];
    str_humidity += incomingPacket[11];
    str_humidity += incomingPacket[12];
    str_humidity += incomingPacket[13];
    str_humidity += incomingPacket[14];

    //Serial.println(str_port);
    //Serial.println(str_temp);
    //Serial.println(str_humidity);

    if (str_port == room1_PORT) {
      lastByteReceivedTimePort1 = millis();
      room1_temperature = str_temp;
      room1_humidity = str_humidity;
    }

    if (str_port == room2_PORT) {
      lastByteReceivedTimePort2 = millis();
      room2_temperature = str_temp;
      room2_humidity = str_humidity;
    }
    delay(5000);
  }

  local_temperature = String(dht.readTemperature());
  local_humidity = String(dht.readHumidity());

  delay(5000);
  //elad natan
}
