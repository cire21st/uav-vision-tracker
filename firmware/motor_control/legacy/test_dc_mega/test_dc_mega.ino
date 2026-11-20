const byte GATE_PIN = 7;
bool gateHigh = false;

void setup() {
  // Start with the MOSFET gate LOW.
  digitalWrite(GATE_PIN, LOW);
  pinMode(GATE_PIN, OUTPUT);

  Serial.begin(115200);
  Serial.println(F("Gate pin: D7 | State: LOW"));
  Serial.println(F("Send a space to toggle HIGH/LOW."));
}

void loop() {
  while (Serial.available() > 0) {
    if (Serial.read() == ' ') {
      gateHigh = !gateHigh;
      digitalWrite(GATE_PIN, gateHigh ? HIGH : LOW);
      Serial.println(gateHigh ? F("D7: HIGH") : F("D7: LOW"));
    }
  }
}
