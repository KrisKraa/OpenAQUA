// OpenAQUA main controller R2 - bring-up firmware (Arduino core for ESP32, v3.x)
//
// Board: ESP32-S3-WROOM-1-N16R8. Pin map: docs/gpio-map.md
// Libraries: Adafruit GFX, Adafruit ILI9341, Adafruit ADS1X15, OneWire, DallasTemperature
//
// What it does
//   - display: pH, TDS (raw, uncalibrated), water temperature, leak status, module ports
//   - RGB button: green = ok, red = leak alarm, blue = maintenance mode (short press toggles,
//     long press acknowledges an alarm)
//   - module ports: VBUS stays OFF until the port's CC line shows an OpenAQUA module
//     (22 kOhm to GND -> ~2.27 V), never switches on for a phone/USB device (5.1 kOhm -> ~1.1 V),
//     and switches off immediately when the module is unplugged (docs/module-port-spec.md)
//   - STUSB4500 (USB-PD sink) presence check on I2C
//
// Same file runs in the Wokwi simulator: set SIMULATION to 1 (simulation/wokwi/).

#define SIMULATION 1

#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include <Adafruit_ADS1X15.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ---------------------------------------------------------------- pins (R2)
// display (CN2)
const int PIN_DISP_SCLK = 4, PIN_DISP_MOSI = 5, PIN_DISP_CS = 6, PIN_DISP_DC = 7;
const int PIN_DISP_RST = 15, PIN_DISP_BL = 16;
// I2C: ADS1115 (0x48), STUSB4500 (0x28)
const int PIN_I2C_SDA = 18, PIN_I2C_SCL = 8;
// sensors
const int PIN_TEMP = 11;         // DS18B20 1-Wire, 4.7k pull-up on board
const int PIN_LEAK1 = 12;        // 1M pull-up on board, water pulls it low
const int PIN_LEAK2 = 13;
const int PIN_TDS_EXCITE = 3;    // AC excitation for the TDS probe
// front button (CN3): switch on IO0 (also BOOT), RGB LED through 220R
const int PIN_BTN = 0;
const int PIN_BTN_R = 38, PIN_BTN_G = 39, PIN_BTN_B = 40;
// status LEDs
const int PIN_LED4 = 17;         // left edge (status)
const int PIN_LED5 = 41;         // port 1 side
const int PIN_LED6 = 21;         // port 2 side
// module ports
const int PIN_P1_CC1 = 1, PIN_P1_CC2 = 2, PIN_P1_EN = 42;   // USBC2, silk "CAN1"
const int PIN_P2_CC1 = 9, PIN_P2_CC2 = 10, PIN_P2_EN = 14;  // USBC3, silk "CAN2"
// CAN (TJA1051T/3) - not used by this bring-up firmware yet
const int PIN_CAN_TX = 47, PIN_CAN_RX = 48;

// ---------------------------------------------------------------- objects
Adafruit_ILI9341 tft(&SPI, PIN_DISP_DC, PIN_DISP_CS, PIN_DISP_RST);
Adafruit_ADS1115 ads;
OneWire oneWire(PIN_TEMP);
DallasTemperature tempSensor(&oneWire);

bool adsOk = false, pdOk = false;

// ---------------------------------------------------------------- module ports
// CC voltage windows (mV) with the controller's 10k pull-up to 3.3 V
const int CC_MODULE_MIN = 2000, CC_MODULE_MAX = 2500;  // OpenAQUA module: 22k Rd -> ~2270 mV
const int CC_SINK_MIN = 800, CC_SINK_MAX = 1600;       // phone / USB device: 5.1k Rd -> ~1110 mV
const uint32_t PORT_ON_DELAY_MS = 500;                  // module must be seen this long

enum PortState { PORT_EMPTY, PORT_MODULE_WAIT, PORT_ON, PORT_REJECTED };
struct Port {
  const char *name; int cc1, cc2, en, led;
  PortState state; uint32_t since; int mv1, mv2;
};
Port ports[2] = {
  {"Port 1", PIN_P1_CC1, PIN_P1_CC2, PIN_P1_EN, PIN_LED5, PORT_EMPTY, 0, 0, 0},
  {"Port 2", PIN_P2_CC1, PIN_P2_CC2, PIN_P2_EN, PIN_LED6, PORT_EMPTY, 0, 0, 0},
};

static bool inWin(int mv, int lo, int hi) { return mv >= lo && mv <= hi; }

static int readCcMv(int pin) {
#if SIMULATION
  return analogRead(pin) * 3300L / 4095;  // Wokwi's ADC is linear 0-3.3 V, its mV calibration is not
#else
  return analogReadMilliVolts(pin);
#endif
}

void updatePort(Port &p) {
  p.mv1 = readCcMv(p.cc1);
  p.mv2 = readCcMv(p.cc2);
  bool module = inWin(p.mv1, CC_MODULE_MIN, CC_MODULE_MAX) || inWin(p.mv2, CC_MODULE_MIN, CC_MODULE_MAX);
  bool sink = inWin(p.mv1, CC_SINK_MIN, CC_SINK_MAX) || inWin(p.mv2, CC_SINK_MIN, CC_SINK_MAX);
  uint32_t now = millis();
  PortState next = p.state;
  if (sink) next = PORT_REJECTED;                       // never power a phone / USB device
  else if (!module) next = PORT_EMPTY;                  // unplugged: off at once
  else if (p.state == PORT_EMPTY || p.state == PORT_REJECTED) { next = PORT_MODULE_WAIT; p.since = now; }
  else if (p.state == PORT_MODULE_WAIT && now - p.since >= PORT_ON_DELAY_MS) next = PORT_ON;
  p.state = next;
  digitalWrite(p.en, p.state == PORT_ON ? HIGH : LOW);
  // LED: on = powered, fast blink = refused device, off = empty / waiting
  bool led = (p.state == PORT_ON) || (p.state == PORT_REJECTED && (now / 150) % 2);
  digitalWrite(p.led, led ? HIGH : LOW);
}

const char *portText(const Port &p) {
  switch (p.state) {
    case PORT_ON: return "module ON ";
    case PORT_MODULE_WAIT: return "module... ";
    case PORT_REJECTED: return "NOT A MODULE";
    default: return "empty     ";
  }
}

// ---------------------------------------------------------------- sensors
float waterTempC = NAN;
float phValue = NAN, phMv = NAN;
float tdsVolts = NAN;
bool leak1 = false, leak2 = false;

// pH: LMP91200 output relative to its common mode (ADS1115 AIN1 - AIN3).
// Ideal electrode: 0 mV at pH 7, -59.16 mV/pH at 25 C. Calibrate later (2-point buffer).
float phFromMv(float mv, float tempC) {
  float slope = -0.1984f * (273.15f + (isnan(tempC) ? 25.0f : tempC));  // mV per pH
  return 7.0f + mv / slope;
}

void readSensors() {
  // non-blocking: read the result of the previous request, then start the next conversion
  // (a blocking read takes ~750 ms and would delay switching a port off on unplug)
  if (tempSensor.getDeviceCount() > 0) {
    float t = tempSensor.getTempCByIndex(0);
    waterTempC = (t == DEVICE_DISCONNECTED_C || t == 85.0f) ? waterTempC : t;
    tempSensor.requestTemperatures();
  }
  leak1 = digitalRead(PIN_LEAK1) == LOW;
  leak2 = digitalRead(PIN_LEAK2) == LOW;
  if (adsOk) {
    ads.setGain(GAIN_EIGHT);                               // +/-0.512 V: pH electrode is +/-415 mV
    int16_t raw = ads.readADC_Differential_1_3();
    phMv = ads.computeVolts(raw) * 1000.0f;
    phValue = phFromMv(phMv, waterTempC);
    ads.setGain(GAIN_ONE);                                 // +/-4.096 V for the TDS channel
    tdsVolts = ads.computeVolts(ads.readADC_SingleEnded(0));
  }
}

// ---------------------------------------------------------------- button + RGB
bool maintenance = false, alarmAck = false;
uint32_t btnDownAt = 0; bool btnWasDown = false;

void setRgb(bool r, bool g, bool b) {
  digitalWrite(PIN_BTN_R, r); digitalWrite(PIN_BTN_G, g); digitalWrite(PIN_BTN_B, b);
}

void handleButton() {
  bool down = digitalRead(PIN_BTN) == LOW;
  uint32_t now = millis();
  if (down && !btnWasDown) btnDownAt = now;
  if (!down && btnWasDown) {
    if (now - btnDownAt > 1000) alarmAck = true;          // long press: acknowledge alarm
    else if (now - btnDownAt > 30) maintenance = !maintenance;
  }
  btnWasDown = down;
  bool leak = leak1 || leak2;
  if (!leak) alarmAck = false;
  if (leak && !alarmAck) setRgb((now / 250) % 2, false, false);  // flashing red
  else if (leak) setRgb(true, false, false);
  else if (maintenance) setRgb(false, false, true);
  else setRgb(false, true, false);
}

// ---------------------------------------------------------------- TDS excitation
// 1 kHz square wave on the probe (keeps it from polarising). The ADS1115 is too slow to sample
// it synchronously - TDS front end is a known open item (docs/r2-design-review.md).
void startTdsExcitation() {
  ledcAttach(PIN_TDS_EXCITE, 1000, 8);
  ledcWrite(PIN_TDS_EXCITE, 128);
}

// ---------------------------------------------------------------- display
void drawStatic() {
  tft.fillScreen(ILI9341_BLACK);
  tft.setTextColor(ILI9341_CYAN); tft.setTextSize(2);
  tft.setCursor(8, 6); tft.print("OpenAQUA");
  tft.setTextSize(1); tft.setTextColor(ILI9341_DARKGREY);
  tft.setCursor(130, 12); tft.print(SIMULATION ? "R2 - simulation" : "R2");
}

// Text drawing in Adafruit_GFX is slow and blocks loop(), so only lines that changed are redrawn.
void drawLine(int line, int y, uint8_t size, uint16_t color, const char *text) {
  static char last[8][40];
  static uint16_t lastColor[8];
  if (lastColor[line] == color && strcmp(last[line], text) == 0) return;
  strlcpy(last[line], text, sizeof last[line]);
  lastColor[line] = color;
  tft.setTextSize(size);
  tft.setTextColor(color, ILI9341_BLACK);
  tft.setCursor(8, y);
  tft.print(text);
}

void drawValues() {
  char buf[40];
  if (isnan(phValue)) snprintf(buf, sizeof buf, "pH   --      ");
  else snprintf(buf, sizeof buf, "pH   %4.2f    ", phValue);
  drawLine(0, 40, 2, ILI9341_WHITE, buf);
  if (isnan(waterTempC)) snprintf(buf, sizeof buf, "Temp --.- C  ");
  else snprintf(buf, sizeof buf, "Temp %4.1f C  ", waterTempC);
  drawLine(1, 65, 2, ILI9341_WHITE, buf);
  if (isnan(tdsVolts)) snprintf(buf, sizeof buf, "TDS  --      ");
  else snprintf(buf, sizeof buf, "TDS  %4.2f V  ", tdsVolts);
  drawLine(2, 90, 2, ILI9341_WHITE, buf);

  bool leak = leak1 || leak2;
  snprintf(buf, sizeof buf, "Leak %s%s     ", leak1 ? "1 " : "", leak2 ? "2" : (leak1 ? "" : "none"));
  drawLine(3, 120, 2, leak ? ILI9341_RED : ILI9341_GREEN, buf);

  for (int i = 0; i < 2; i++) {
    Port &p = ports[i];
    snprintf(buf, sizeof buf, "%s: %s CC %4d/%4d mV ", p.name, portText(p), p.mv1, p.mv2);
    drawLine(4 + i, 155 + i * 14, 1, p.state == PORT_ON ? ILI9341_GREEN : p.state == PORT_REJECTED ? ILI9341_RED : ILI9341_LIGHTGREY, buf);
  }
  snprintf(buf, sizeof buf, "ADC %s  PD %s  %s   ", adsOk ? "ok" : "--", pdOk ? "ok" : "--", maintenance ? "MAINTENANCE" : "           ");
  drawLine(6, 190, 1, ILI9341_DARKGREY, buf);
}

// ---------------------------------------------------------------- setup / loop
void setup() {
  Serial.begin(115200);
  // outputs: ports OFF first (also held off by hardware pull-downs)
  for (Port &p : ports) { pinMode(p.en, OUTPUT); digitalWrite(p.en, LOW); pinMode(p.led, OUTPUT); }
  for (Port &p : ports) { analogSetPinAttenuation(p.cc1, ADC_11db); analogSetPinAttenuation(p.cc2, ADC_11db); }
  pinMode(PIN_LED4, OUTPUT);
  pinMode(PIN_BTN_R, OUTPUT); pinMode(PIN_BTN_G, OUTPUT); pinMode(PIN_BTN_B, OUTPUT);
  pinMode(PIN_BTN, INPUT_PULLUP);
#if SIMULATION
  pinMode(PIN_LEAK1, INPUT_PULLUP); pinMode(PIN_LEAK2, INPUT_PULLUP);   // simulator has no 1M resistors
#else
  pinMode(PIN_LEAK1, INPUT); pinMode(PIN_LEAK2, INPUT);                 // board has 1M pull-ups; an internal ~45k one would kill sensitivity
#endif

  pinMode(PIN_DISP_BL, OUTPUT); digitalWrite(PIN_DISP_BL, HIGH);
  SPI.begin(PIN_DISP_SCLK, -1, PIN_DISP_MOSI, PIN_DISP_CS);
  tft.begin(40000000);
  tft.setRotation(1);
  drawStatic();

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  adsOk = ads.begin(0x48, &Wire);
  Wire.beginTransmission(0x28);
  pdOk = (Wire.endTransmission() == 0);
  tempSensor.begin();
  tempSensor.setWaitForConversion(false);
  tempSensor.requestTemperatures();
  startTdsExcitation();
  Serial.printf("OpenAQUA R2 up. ADS1115 %s, STUSB4500 %s, DS18B20 x%d\n",
                adsOk ? "found" : "MISSING", pdOk ? "found" : "missing", tempSensor.getDeviceCount());
}

void loop() {
  static uint32_t lastSensors = 0, lastDraw = 0;
  uint32_t now = millis();
  for (Port &p : ports) updatePort(p);      // every loop: fast switch-off on unplug
  handleButton();
  digitalWrite(PIN_LED4, (now / 1000) % 2);  // heartbeat
  if (now - lastSensors > 1000) { lastSensors = now; readSensors(); }
  if (now - lastDraw > 300) { lastDraw = now; drawValues(); }
  delay(5);
}
