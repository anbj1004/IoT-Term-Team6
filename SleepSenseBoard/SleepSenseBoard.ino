#include <WiFi.h>
#include <PubSubClient.h>
#include <time.h>
#include <ArduinoJson.h>

#define LIGHT_SENSOR_PIN 33
#define BUZZER_PIN 25  // 부저 핀

const char* ssid = "AndroidHotspotEB_4A_03";
const char* password = "11113111";
const char* mqtt_server = "192.168.78.221";

WiFiClient espClient;
PubSubClient client(espClient);

const int threshold = 1000; // 조도 임계값
unsigned long startTime = 0;
unsigned long usedSec = 0;
bool inUse = false;

int timerThresholdMin = 5; // 기본 타이머 5분 (웹서버 기본값과 동일하게 맞춤)

const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 9 * 3600;
const int daylightOffset_sec = 0;

void setup_wifi() {
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
}

void callback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(msg);

  if (String(topic) == "/phone/timer_setting") {
    int newTimer = msg.toInt();
    if (newTimer > 0) {
      timerThresholdMin = newTimer;
      Serial.print("Timer threshold updated to: ");
      Serial.print(timerThresholdMin);
      Serial.println(" minutes");
    }
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect("ESP32_A_Client")) {
      Serial.println("connected");
      client.subscribe("/phone/timer_setting");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LIGHT_SENSOR_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  setup_wifi();

  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);

  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  int lightValue = analogRead(LIGHT_SENSOR_PIN);
  Serial.print("Light: ");
  Serial.println(lightValue);

  if (lightValue > threshold) {
    if (!inUse) {
      inUse = true;
      startTime = millis();
      Serial.println("Smartphone usage started");
    }
    usedSec = (millis() - startTime) / 1000;

    // 타이머 임계값 (분) 도달 시 부저 울리기
    if (usedSec >= timerThresholdMin * 60) {
      digitalWrite(BUZZER_PIN, HIGH);  // 부저 ON
    } else {
      digitalWrite(BUZZER_PIN, LOW);   // 부저 OFF
    }

    static unsigned long lastSend = 0;
    if (millis() - lastSend > 30000) {
      lastSend = millis();

      String dateStr, timeStr;
      struct tm timeinfo;
      if (getLocalTime(&timeinfo)) {
        char dateBuffer[11];
        char timeBuffer[9];
        strftime(dateBuffer, sizeof(dateBuffer), "%Y-%m-%d", &timeinfo);
        strftime(timeBuffer, sizeof(timeBuffer), "%H:%M:%S", &timeinfo);
        dateStr = String(dateBuffer);
        timeStr = String(timeBuffer);
      } else {
        dateStr = "1970-01-01";
        timeStr = "00:00:00";
      }

      StaticJsonDocument<200> doc;
      doc["client_id"] = "ESP32_A";
      doc["usage_date"] = dateStr;
      doc["start_time"] = timeStr;
      doc["used_sec"] = usedSec;

      char jsonBuffer[256];
      serializeJson(doc, jsonBuffer);

      client.publish("sleep_sense/data", jsonBuffer);

      Serial.print("Published data: ");
      Serial.println(jsonBuffer);
    }

  } else {
    if (inUse) {
      Serial.print("Smartphone usage ended. Total seconds: ");
      Serial.println(usedSec);
      inUse = false;
      usedSec = 0;
      startTime = 0;
      digitalWrite(BUZZER_PIN, LOW);  // 부저 끄기
    }
  }

  delay(1000);
}
