#include "ESP32_NOW.h"
#include "WiFi.h"
#include <esp_mac.h>

/* --- Config --- */
#define ESPNOW_WIFI_CHANNEL     11
#define SEND_INTERVAL_MS        20
#define HALL_SENSOR_PIN         1
#define PULSES_PER_REV          4
#define PULSE_REPORT_INTERVAL_MS 100

#define PULSES_PER_KCAL         150   // 150 pulses for 1 kcal
#define KCAL_THRESHOLD_STEP     50  // Trigger every 50 kcal

/* --- Message Structure --- */
typedef struct __attribute__((packed)) {
  char type;
  union {
    float rpm;
    struct {
      uint8_t clientNo;
      uint8_t closed;
    } cmd;
  } data;
} message_t;

/* --- Broadcast Peer --- */
class ESP_NOW_Broadcast_Peer : public ESP_NOW_Peer {
public:
  ESP_NOW_Broadcast_Peer(uint8_t channel, wifi_interface_t iface, const uint8_t *lmk)
    : ESP_NOW_Peer(ESP_NOW.BROADCAST_ADDR, channel, iface, lmk) {}
  ~ESP_NOW_Broadcast_Peer() { remove(); }
  bool begin() { return ESP_NOW.begin() && add(); }
  bool send_message(const uint8_t *data, size_t len) { return send(data, len); }
};

ESP_NOW_Broadcast_Peer broadcast_peer(ESPNOW_WIFI_CHANNEL, WIFI_IF_STA, NULL);

/* --- State Variables --- */
volatile int pulseCount = 0;
volatile unsigned long totalPulses = 0;

unsigned long lastSent = 0;
unsigned long lastRPMUpdate = 0;
unsigned long lastPulseReport = 0;
float currentRPM = 0.0;

unsigned int openedBoxCount = 0;

#define RPM_SMOOTH_COUNT 10
float rpmHistory[RPM_SMOOTH_COUNT] = {0};
int rpmIndex = 0;
bool rpmFilled = false;

/* --- Interrupt Handler --- */
void IRAM_ATTR onPulseDetected() {
  pulseCount++;
  totalPulses++;
}

/* --- Helpers --- */
float calculateRPM() {
  unsigned long now = millis();
  float elapsed = (now - lastRPMUpdate) / 1000.0;
  lastRPMUpdate = now;
  float revs = (float)pulseCount / PULSES_PER_REV;
  pulseCount = 0;
  return (revs / elapsed) * 60.0;
}

float getMovingAverage() {
  int count = rpmFilled ? RPM_SMOOTH_COUNT : rpmIndex;
  float sum = 0;
  for (int i = 0; i < count; i++) sum += rpmHistory[i];
  return count > 0 ? sum / count : 0;
}

float getTotalKcal() {
  return totalPulses / (float)PULSES_PER_KCAL;
}

void sendOpenCommand(uint8_t boxNo) {
  message_t cmd;
  cmd.type = 'C';
  cmd.data.cmd.clientNo = boxNo;
  cmd.data.cmd.closed = 0;  // 열림
  Serial.printf("AUTO CMD: OPEN box %d (%.2f kcal)\n", boxNo, getTotalKcal());

  if (!broadcast_peer.send_message((uint8_t*)&cmd, sizeof(cmd))) {
    Serial.println("ERROR: Auto CMD send failed");
  }
}

/* --- Setup --- */
void setup() {
  Serial.begin(115200);
  pinMode(HALL_SENSOR_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(HALL_SENSOR_PIN), onPulseDetected, FALLING);

  WiFi.mode(WIFI_STA);
  WiFi.setChannel(ESPNOW_WIFI_CHANNEL);
  while (!WiFi.STA.started()) delay(100);

  if (!broadcast_peer.begin()) {
    Serial.println("ERROR: ESP-NOW init failed");
    delay(3000);
    ESP.restart();
  }
}

/* --- Loop --- */
void loop() {
  if (millis() - lastSent >= SEND_INTERVAL_MS) {
    lastSent = millis();

    currentRPM = calculateRPM();
    rpmHistory[rpmIndex] = currentRPM;
    rpmIndex = (rpmIndex + 1) % RPM_SMOOTH_COUNT;
    if (rpmIndex == 0) rpmFilled = true;

    float avgRPM = getMovingAverage();

    message_t msg;
    msg.type = 'R';
    msg.data.rpm = avgRPM;

    Serial.printf("RPM: %.2f\n", avgRPM);

    if (!broadcast_peer.send_message((uint8_t*)&msg, sizeof(msg))) {
      Serial.println("ERROR: RPM send failed");
    }
  }

  if (millis() - lastPulseReport >= PULSE_REPORT_INTERVAL_MS) {
    lastPulseReport = millis();
    noInterrupts();
    unsigned long currentTotal = totalPulses;
    interrupts();
    float kcal = currentTotal / (float)PULSES_PER_KCAL;
    Serial.printf("PULSE: %lu\tKCAL: %.2f\n", currentTotal, kcal);

    // Trigger next box if kcal exceeds threshold
    float targetKcal = KCAL_THRESHOLD_STEP * (openedBoxCount + 1);
    if (kcal >= targetKcal) {
      openedBoxCount++;
      sendOpenCommand(openedBoxCount);
    }
  }

  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() > 0) {
      int comma = input.indexOf(',');
      if (comma > 0) {
        int clientNo = input.substring(0, comma).toInt();
        int state = input.substring(comma + 1).toInt();

        message_t cmd;
        cmd.type = 'C';
        cmd.data.cmd.clientNo = (uint8_t)clientNo;
        cmd.data.cmd.closed = (uint8_t)state;

        Serial.printf("CMD: %d,%d\n", clientNo, state);
        if (!broadcast_peer.send_message((uint8_t*)&cmd, sizeof(cmd))) {
          Serial.println("ERROR: CMD send failed");
        }
      }
    }
  }
}