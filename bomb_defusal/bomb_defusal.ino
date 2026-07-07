/*
  Bomb Defusal Game — Arduino Uno
  Level 1: pull the correct wire (3 wires, wrong pull = -30s)
  Level 2: Simon Says (5-step sequence, mistake = restart the sequence)
  Servo pops the box open between levels.
*/

#include <LiquidCrystal.h>
#include <Servo.h>

// ---------- Pin map ----------
const uint8_t WIRE_PIN[3]      = {2, 3, 4};      // red, blue, yellow wires
const uint8_t SIMON_LED_PIN[4] = {5, 6, 7, A0};  // red, green, blue, yellow
const uint8_t SIMON_BTN_PIN[4] = {A1, A2, A3, A4};
const uint8_t SERVO_PIN        = A5;

LiquidCrystal lcd(8, 9, 10, 11, 12, 13); // RS, EN, D4, D5, D6, D7
Servo lidServo;

// ---------- Game settings ----------
const long  GAME_TIME_SECONDS   = 180;  // 3:00 starting time
const long  WRONG_WIRE_PENALTY  = 30;   // seconds deducted per wrong wire
const uint8_t SEQUENCE_LENGTH   = 5;
const int   SERVO_CLOSED_ANGLE  = 0;
const int   SERVO_OPEN_ANGLE    = 90;
const unsigned long BOX_OPEN_WAIT_MS = 4000; // pause before level 2 starts

// ---------- Game state ----------
enum GameState { LEVEL1, UNLOCKING, LEVEL2_SHOW, LEVEL2_INPUT, WON, LOST };
GameState state = LEVEL1;

unsigned long gameStartMillis;
long penaltySeconds = 0;
long lastShownRemaining = -1;

int  correctWireIndex;
bool wireTriggered[3] = {false, false, false};

int sequence[SEQUENCE_LENGTH];
uint8_t playerStep = 0;

unsigned long stateChangedAt = 0;

void setup() {
  randomSeed(analogRead(A0)); // grab noise before A0 becomes a digital button pin

  for (uint8_t i = 0; i < 3; i++) pinMode(WIRE_PIN[i], INPUT_PULLUP);
  for (uint8_t i = 0; i < 4; i++) {
    pinMode(SIMON_LED_PIN[i], OUTPUT);
    pinMode(SIMON_BTN_PIN[i], INPUT_PULLUP);
    digitalWrite(SIMON_LED_PIN[i], LOW);
  }

  lidServo.attach(SERVO_PIN);
  lidServo.write(SERVO_CLOSED_ANGLE);

  lcd.begin(16, 2);

  correctWireIndex = random(0, 3);

  gameStartMillis = millis();
  startLevel1();
}

void loop() {
  switch (state) {
    case LEVEL1:       handleLevel1();      break;
    case UNLOCKING:    handleUnlocking();   break;
    case LEVEL2_SHOW:  handleLevel2Show();  break;
    case LEVEL2_INPUT: handleLevel2Input(); break;
    case WON:          /* idle */           break;
    case LOST:         /* idle */           break;
  }

  if (state == LEVEL1 || state == LEVEL2_SHOW || state == LEVEL2_INPUT) {
    updateTimerRow();
    if (timeRemaining() <= 0) {
      triggerLose();
    }
  }
}

// ---------- Timer helpers ----------
long timeRemaining() {
  long elapsed = (millis() - gameStartMillis) / 1000;
  long remaining = GAME_TIME_SECONDS - penaltySeconds - elapsed;
  return remaining < 0 ? 0 : remaining;
}

void updateTimerRow() {
  long remaining = timeRemaining();
  if (remaining == lastShownRemaining) return;
  lastShownRemaining = remaining;

  int m = remaining / 60;
  int s = remaining % 60;
  lcd.setCursor(11, 0);
  if (m < 10) lcd.print('0');
  lcd.print(m);
  lcd.print(':');
  if (s < 10) lcd.print('0');
  lcd.print(s);
}

// ---------- Level 1: wires ----------
void startLevel1() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("LVL1");
  lcd.setCursor(0, 1);
  lcd.print("Pull the wire!");
  lastShownRemaining = -1;
}

void handleLevel1() {
  for (uint8_t i = 0; i < 3; i++) {
    if (wireTriggered[i]) continue;
    if (digitalRead(WIRE_PIN[i]) == HIGH) { // wire disconnected = pulled
      delay(30); // debounce
      if (digitalRead(WIRE_PIN[i]) != HIGH) continue; // false trigger
      wireTriggered[i] = true;

      if ((int)i == correctWireIndex) {
        lcd.setCursor(0, 1);
        lcd.print("Correct! Open...");
        startUnlocking();
      } else {
        penaltySeconds += WRONG_WIRE_PENALTY;
        lcd.setCursor(0, 1);
        lcd.print("WRONG! -30s     ");
        delay(1200);
        lcd.setCursor(0, 1);
        lcd.print("Pull the wire!  ");
      }
    }
  }
}

// ---------- Between levels: servo unlocks the box ----------
void startUnlocking() {
  state = UNLOCKING;
  stateChangedAt = millis();
  lidServo.write(SERVO_OPEN_ANGLE);
}

void handleUnlocking() {
  if (millis() - stateChangedAt >= BOX_OPEN_WAIT_MS) {
    startLevel2();
  }
}

// ---------- Level 2: Simon Says ----------
void startLevel2() {
  for (uint8_t i = 0; i < SEQUENCE_LENGTH; i++) sequence[i] = random(0, 4);
  playerStep = 0;
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("LVL2");
  state = LEVEL2_SHOW;
  stateChangedAt = 0; // force immediate show
}

void handleLevel2Show() {
  lcd.setCursor(0, 1);
  lcd.print("Watch closely..");
  for (uint8_t i = 0; i < SEQUENCE_LENGTH; i++) {
    flashLed(sequence[i], 400);
    delay(200);
  }
  lcd.setCursor(0, 1);
  lcd.print("Your turn!      ");
  state = LEVEL2_INPUT;
}

void handleLevel2Input() {
  for (uint8_t i = 0; i < 4; i++) {
    if (digitalRead(SIMON_BTN_PIN[i]) == LOW) {
      delay(30); // debounce
      if (digitalRead(SIMON_BTN_PIN[i]) != LOW) continue;

      flashLed(i, 200);

      if ((int)i == sequence[playerStep]) {
        playerStep++;
        if (playerStep == SEQUENCE_LENGTH) {
          triggerWin();
          return;
        }
      } else {
        lcd.setCursor(0, 1);
        lcd.print("Oops! Restart.. ");
        delay(1000);
        playerStep = 0;
        state = LEVEL2_SHOW;
      }

      while (digitalRead(SIMON_BTN_PIN[i]) == LOW) delay(5); // wait for release
    }
  }
}

void flashLed(uint8_t colorIndex, uint16_t onTimeMs) {
  digitalWrite(SIMON_LED_PIN[colorIndex], HIGH);
  delay(onTimeMs);
  digitalWrite(SIMON_LED_PIN[colorIndex], LOW);
}

// ---------- End states ----------
void triggerWin() {
  state = WON;
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("BOMB DEFUSED!");
  lcd.setCursor(0, 1);
  lcd.print("YOU WIN :)");
  for (uint8_t r = 0; r < 3; r++) {
    for (uint8_t i = 0; i < 4; i++) digitalWrite(SIMON_LED_PIN[i], HIGH);
    delay(200);
    for (uint8_t i = 0; i < 4; i++) digitalWrite(SIMON_LED_PIN[i], LOW);
    delay(200);
  }
}

void triggerLose() {
  state = LOST;
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("TIME UP - BOOM!");
  lcd.setCursor(0, 1);
  lcd.print("GAME OVER");
  for (uint8_t i = 0; i < 4; i++) digitalWrite(SIMON_LED_PIN[i], HIGH);
}
