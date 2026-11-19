#include <Servo.h>
#include <stdlib.h>
#include <string.h>

// Arduino Uno R3. Motor 1 = Tilt; Motor 2 = Pan.
const byte MOTOR1_EN = 2;
const byte MOTOR1_STP = 3;
const byte MOTOR1_DIR = 4;
const byte MOTOR2_EN = 5;
const byte MOTOR2_STP = 6;
const byte MOTOR2_DIR = 7;
const byte MOTOR3_SERVO_PIN = 9;  // SG90 360 continuous-rotation servo signal
const byte STATUS_LED_PIN = LED_BUILTIN;

const int MAX_STEP_RATE = 1200;
const unsigned long STEP_HIGH_US = 100;
const unsigned long STEP_LOW_MIN_US = 100;
const unsigned long CONTROL_TIMEOUT_MS = 500;

// Continuous servo timing: calibrate these with your SG90 and power supply.
// TowerPro publishes 110 RPM at 4.8 V (about 545 ms/rev); 550 ms is a starting value.
const int M3_STOP_US = 1500;       // adjust slightly if the servo creeps at rest
const int M3_FORWARD_US = 2000;    // full speed in one direction
const unsigned long M3_TURN_MS = 550;

struct StepperAxis {
  byte enablePin;
  byte stepPin;
  byte dirPin;
  int speedStepsPerSec;
  bool pulseHigh;
  byte lastDirLevel;
  unsigned long nextStepAtUs;
  unsigned long pulseOffAtUs;
  unsigned long dirReadyAtUs;
};

// Positive speed uses DIR=LOW, matching the supplied CW test.
StepperAxis tiltAxis = {MOTOR1_EN, MOTOR1_STP, MOTOR1_DIR, 0, false, LOW, 0, 0, 0};
StepperAxis panAxis  = {MOTOR2_EN, MOTOR2_STP, MOTOR2_DIR, 0, false, LOW, 0, 0, 0};
Servo motor3;
bool motor3Busy = false;
unsigned long motor3StopAtMs = 0;

char lineBuffer[40];
byte lineLength = 0;
unsigned long lastControlMs = 0;
int lastPanSpeed = 0;
int lastTiltSpeed = 0;
unsigned long ledOffAtMs = 0;

void initializeAxis(StepperAxis &axis) {
  pinMode(axis.enablePin, OUTPUT);
  pinMode(axis.stepPin, OUTPUT);
  pinMode(axis.dirPin, OUTPUT);
  digitalWrite(axis.stepPin, LOW);
  digitalWrite(axis.dirPin, LOW);
  digitalWrite(axis.enablePin, LOW);  // EN active LOW per supplied driver test
  axis.speedStepsPerSec = 0;
  axis.pulseHigh = false;
  axis.lastDirLevel = LOW;
  axis.nextStepAtUs = micros() + 10;
  axis.pulseOffAtUs = 0;
  axis.dirReadyAtUs = axis.nextStepAtUs;
}

void updateAxis(StepperAxis &axis) {
  unsigned long now = micros();
  if (axis.pulseHigh) {
    if ((long)(now - axis.pulseOffAtUs) >= 0) {
      digitalWrite(axis.stepPin, LOW);
      axis.pulseHigh = false;
    }
    return;
  }
  if (axis.speedStepsPerSec == 0) return;

  bool positive = axis.speedStepsPerSec > 0;
  byte wantedDir = positive ? LOW : HIGH;
  if (axis.lastDirLevel != wantedDir) {
    digitalWrite(axis.dirPin, wantedDir);
    axis.lastDirLevel = wantedDir;
    axis.dirReadyAtUs = now + 10;
    return;
  }

  unsigned long intervalUs = 1000000UL / abs(axis.speedStepsPerSec);
  const unsigned long minInterval = STEP_HIGH_US + STEP_LOW_MIN_US;
  if (intervalUs < minInterval) intervalUs = minInterval;
  if ((long)(now - axis.nextStepAtUs) >= 0 && (long)(now - axis.dirReadyAtUs) >= 0) {
    digitalWrite(axis.stepPin, HIGH);
    axis.pulseHigh = true;
    axis.pulseOffAtUs = now + STEP_HIGH_US;
    axis.nextStepAtUs = now + intervalUs;
  }
}

void startMotor3Turn() {
  if (motor3Busy) {
    Serial.println("ACK,X,BUSY");
    return;
  }
  motor3.writeMicroseconds(M3_FORWARD_US);
  motor3Busy = true;
  motor3StopAtMs = millis() + M3_TURN_MS;
  Serial.println("ACK,X,STARTED");
}

void processLine(char *line) {
  if (line[0] == '\0') return;
  if (strcmp(line, "X") == 0) {
    startMotor3Turn();
    return;
  }

  // Protocol: V,<pan steps/s>,<tilt steps/s>; centered stick sends zero speed.
  if (line[0] != 'V' || line[1] != ',') return;
  char *comma = strchr(line + 2, ',');
  if (comma == nullptr) return;
  *comma = '\0';
  char *endPan;
  char *endTilt;
  long pan = strtol(line + 2, &endPan, 10);
  long tilt = strtol(comma + 1, &endTilt, 10);
  if (*endPan != '\0' || *endTilt != '\0') return;

  pan = constrain(pan, -MAX_STEP_RATE, MAX_STEP_RATE);
  tilt = constrain(tilt, -MAX_STEP_RATE, MAX_STEP_RATE);
  if (pan != lastPanSpeed || tilt != lastTiltSpeed) {
    digitalWrite(STATUS_LED_PIN, HIGH);
    ledOffAtMs = millis() + 150;
  }
  lastPanSpeed = (int)pan;
  lastTiltSpeed = (int)tilt;
  panAxis.speedStepsPerSec = lastPanSpeed;
  tiltAxis.speedStepsPerSec = lastTiltSpeed;
  lastControlMs = millis();

  Serial.print("ACK,V,");
  Serial.print(lastPanSpeed);
  Serial.print(',');
  Serial.println(lastTiltSpeed);
}

void setup() {
  Serial.begin(115200);
  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW);
  initializeAxis(tiltAxis);
  initializeAxis(panAxis);
  motor3.attach(MOTOR3_SERVO_PIN);
  motor3.writeMicroseconds(M3_STOP_US);
  lastControlMs = millis();
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      lineBuffer[lineLength] = '\0';
      processLine(lineBuffer);
      lineLength = 0;
    } else if (c != '\r') {
      if (lineLength < sizeof(lineBuffer) - 1) lineBuffer[lineLength++] = c;
      else lineLength = 0;
    }
  }

  // Stop both stepper axes on standby, controller disconnect, or serial timeout.
  if (millis() - lastControlMs > CONTROL_TIMEOUT_MS) {
    panAxis.speedStepsPerSec = 0;
    tiltAxis.speedStepsPerSec = 0;
  }
  updateAxis(tiltAxis);
  updateAxis(panAxis);

  if (motor3Busy && (long)(millis() - motor3StopAtMs) >= 0) {
    motor3.writeMicroseconds(M3_STOP_US);
    motor3Busy = false;
    Serial.println("ACK,X,DONE");
  }

  if (digitalRead(STATUS_LED_PIN) == HIGH && (long)(millis() - ledOffAtMs) >= 0) {
    digitalWrite(STATUS_LED_PIN, LOW);
  }
}
