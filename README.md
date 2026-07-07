# Bomb Defusal Box — Arduino Uno

A 2-level prop game:
- **Level 1 — Wires:** 3 wires, one is correct. Pull the wrong one and 30s is deducted from the timer. Pull the correct one to unlock the box.
- **Unlock:** an SG90 servo pops the lid, then a few seconds pause before Level 2 starts.
- **Level 2 — Simon Says:** a 5-step LED sequence plays, then you must repeat it on the matching buttons. Any mistake restarts the sequence from step 1. Complete it once to win.
- A 16x2 LCD shows the countdown timer at all times, plus status messages ("WRONG! -30s", "Watch closely..", "BOMB DEFUSED!", etc).

Code: [`bomb_defusal/bomb_defusal.ino`](bomb_defusal/bomb_defusal.ino)

> **Note on Level 2 design:** I implemented it as a *fixed* 5-step sequence generated once — if you mess up, it replays the same 5 steps from the start (matches "resetted to the first sequence again"). If you actually wanted the classic *growing* Simon Says (round 1 shows 1 step, round 2 shows 2 steps, etc., building up to 5), tell me and I'll adjust — it's a small change.

## Pin map (Arduino Uno)

This uses every non-serial pin on the Uno (D0/D1 are left free for USB/Serial debugging).

| Arduino Pin | Connects to |
|---|---|
| D2 | Wire 1 (red) |
| D3 | Wire 2 (blue) |
| D4 | Wire 3 (yellow) |
| D5 | Simon LED — Red (through 220Ω resistor) |
| D6 | Simon LED — Green (through 220Ω resistor) |
| D7 | Simon LED — Blue (through 220Ω resistor) |
| D8 | LCD1602 pin RS |
| D9 | LCD1602 pin E (Enable) |
| D10 | LCD1602 pin D4 |
| D11 | LCD1602 pin D5 |
| D12 | LCD1602 pin D6 |
| D13 | LCD1602 pin D7 |
| A0 | Simon LED — Yellow (through 220Ω resistor) |
| A1 | Simon Button — Red, **signal (S) pin** |
| A2 | Simon Button — Green, **signal (S) pin** |
| A3 | Simon Button — Blue, **signal (S) pin** |
| A4 | Simon Button — Yellow, **signal (S) pin** |
| A5 | SG90 Servo signal (orange wire) |
| 5V | LCD VDD, LCD backlight A, servo V+ (red), pot outer legs, **all 4 button modules' VCC (middle pin)** |
| GND | LCD VSS, LCD R/W, all wire far ends, all LED cathodes, servo GND (brown/black), pot outer legs, **all 4 button modules' "−" pin** |

**Wires (Level 1) use the Uno's internal pull-up resistor** (`INPUT_PULLUP` in the code) — each wire just needs two ends: one to its Arduino pin, one to GND. A wire reads "pulled" the instant it's disconnected from GND.

**Buttons (Level 2) are 3-pin tactile breakout modules**, not bare switches — each has its own onboard pull-down resistor and 3 pins: **S** (signal → the Arduino pin in the table above), **middle pin** (VCC → 5V), and **"−"** (GND). Because the module supplies its own pull-down, the code reads it as `INPUT` (not `INPUT_PULLUP`) and treats the signal as **idle = LOW, pressed = HIGH** — the opposite polarity from the wires. If your specific module turns out to be wired the other way (idle HIGH, pressed LOW), it's a one-line fix in `handleLevel2Input()` — swap the `HIGH`/`LOW` checks.

## Bill of materials & rough quote

Prices are ballpark USD for budget/clone parts from a generic electronics supplier — swap in your local supplier's actual prices.

| Qty | Part | Est. unit price | Est. total |
|---|---|---|---|
| 1 | Arduino Uno (or clone) | $6–25 | $6–25 |
| 1 | LCD1602 (parallel, no I2C backpack) | $2–4 | $2–4 |
| 1 | 10kΩ potentiometer (LCD contrast) | $0.30 | $0.30 |
| 1 | SG90 micro servo | $2–4 | $2–4 |
| 4 | 5mm LEDs (R/G/B/Y) | $0.05 | $0.20 |
| 4 | 220Ω resistors (LED current limiting) | $0.02 | $0.08 |
| 1 | 220Ω resistor (LCD backlight, if not onboard) | $0.02 | $0.02 |
| 3 | "Wires" for Level 1 (any 2-conductor wire/lead) | $0.10 | $0.30 |
| 4 | 3-pin tactile button breakout modules | $0.30–0.60 | $1.20–2.40 |
| 1 | Breadboard (half or full size) | $2–4 | $2–4 |
| 1 | Jumper wire pack (M-M, M-F) | $2–4 | $2–4 |
| 1 | 9V battery + clip or USB power bank (standalone play) | $3–6 | $3–6 |
| — | Project box/enclosure, hinge/latch for the lid | varies | varies |
| **Total (excl. enclosure)** | | | **~$26–58** |

Button prices assume a generic 3-pin tactile breakout module (S/VCC/GND); confirm against what you actually source.

## Assembly notes (since your LEDs/buttons are remote from the breadboard)

Since your LEDs and buttons live in the box/lid and only reach the breadboard via extension wire:
1. Solder or crimp a wire lead to each LED leg (2 wires each) and to each button module's 3 pins (S, VCC, GND) — or use small 3-pin JST/Dupont connectors so the lid can still be disconnected from the base for maintenance.
2. Bundle and label each component's wires (e.g. a small tape flag: "LED-R", "BTN-R S/V/G") so you don't cross-wire colors or swap a button's S and VCC when it's time to plug into the breadboard — swapping those two on this module won't damage anything, but the button just won't respond.
3. On the breadboard, land the resistor for each LED right at the breadboard end of its wire (resistor in-line between the Arduino signal pin and the LED anode wire), not out at the LED — keeps the remote LED wiring as simple 2-conductor runs.
4. Run all the "return" legs (LED cathodes, button GND pins, wire far ends) to a shared GND rail on the breadboard, and all 4 buttons' VCC pins to a shared 5V rail, rather than routing each one back individually — one common bus of each is enough.
5. Keep wire runs under ~1m if possible; at breadboard-prototype voltages/currents this project is very tolerant, but shorter runs are easier to manage physically inside a small box.

## Uploading

1. Install the **Servo** and **LiquidCrystal** libraries (both ship with the Arduino IDE by default — no install needed).
2. Wire per the pin map above.
3. Open `bomb_defusal/bomb_defusal.ino` in the Arduino IDE, select **Arduino Uno** as the board, select the correct port, and upload.
4. Adjust `GAME_TIME_SECONDS`, `WRONG_WIRE_PENALTY`, `SEQUENCE_LENGTH`, or `BOX_OPEN_WAIT_MS` at the top of the file to retune difficulty/timing.
