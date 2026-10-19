// Wokwi custom chip: TI ADS1115 16-bit I2C ADC (address 0x48)
// Enough of the register map for the Adafruit_ADS1X15 library:
// pointer 0 = conversion, 1 = config, 2/3 = thresholds; single-shot and continuous mode,
// all MUX settings and PGA ranges. Inputs are read as voltages from the AIN0..AIN3 pins.
#include "wokwi-api.h"
#include <stdint.h>
#include <stdlib.h>

typedef struct {
  pin_t ain[4];
  uint8_t ptr;
  uint8_t rbyte;
  uint8_t wcount;
  uint8_t wbuf[2];
  uint16_t config, conv, lo, hi;
} chip_t;

static const float FSR[8] = {6.144f, 4.096f, 2.048f, 1.024f, 0.512f, 0.256f, 0.256f, 0.256f};

// Wokwi's analog values are a 0..1 ratio that pin_adc_read() reports on a 5 V scale; this
// circuit runs at 3.3 V (a knob at the top reads 5.0 otherwise).
static float vin(chip_t *c, int i) { return pin_adc_read(c->ain[i]) * (3.3f / 5.0f); }

static void convert(chip_t *c) {
  int mux = (c->config >> 12) & 7, pga = (c->config >> 9) & 7;
  float v;
  switch (mux) {
    case 0: v = vin(c, 0) - vin(c, 1); break;
    case 1: v = vin(c, 0) - vin(c, 3); break;
    case 2: v = vin(c, 1) - vin(c, 3); break;
    case 3: v = vin(c, 2) - vin(c, 3); break;
    default: v = vin(c, mux - 4); break;
  }
  float code = v / FSR[pga] * 32768.0f;
  if (code > 32767.0f) code = 32767.0f;
  if (code < -32768.0f) code = -32768.0f;
  c->conv = (uint16_t)(int16_t)code;
}

static bool on_connect(void *user, uint32_t address, bool read) {
  chip_t *c = user;
  c->rbyte = 0;
  c->wcount = 0;
  return true;
}

static uint8_t on_read(void *user) {
  chip_t *c = user;
  uint16_t reg;
  switch (c->ptr) {
    case 0:
      if (c->rbyte == 0 && !(c->config & 0x0100)) convert(c);  // continuous mode
      reg = c->conv; break;
    case 1: reg = c->config | 0x8000; break;  // OS = 1: conversion finished
    case 2: reg = c->lo; break;
    default: reg = c->hi; break;
  }
  uint8_t b = (c->rbyte == 0) ? (uint8_t)(reg >> 8) : (uint8_t)(reg & 0xFF);
  c->rbyte++;
  return b;
}

static bool on_write(void *user, uint8_t data) {
  chip_t *c = user;
  if (c->wcount == 0) {
    c->ptr = data & 3;
  } else if (c->wcount <= 2) {
    c->wbuf[c->wcount - 1] = data;
    if (c->wcount == 2) {
      uint16_t v = ((uint16_t)c->wbuf[0] << 8) | c->wbuf[1];
      if (c->ptr == 1) {
        c->config = v & 0x7FFF;
        if (v & 0x8000) convert(c);  // start single-shot conversion
      } else if (c->ptr == 2) c->lo = v;
      else if (c->ptr == 3) c->hi = v;
    }
  }
  c->wcount++;
  return true;
}

static void on_disconnect(void *user) {}

void chip_init(void) {
  chip_t *c = calloc(1, sizeof(chip_t));
  c->config = 0x8583;  // power-on default
  c->lo = 0x8000;
  c->hi = 0x7FFF;
  c->ain[0] = pin_init("AIN0", ANALOG);
  c->ain[1] = pin_init("AIN1", ANALOG);
  c->ain[2] = pin_init("AIN2", ANALOG);
  c->ain[3] = pin_init("AIN3", ANALOG);
  const i2c_config_t cfg = {
    .user_data = c,
    .address = 0x48,
    .scl = pin_init("SCL", INPUT),
    .sda = pin_init("SDA", INPUT),
    .connect = on_connect,
    .read = on_read,
    .write = on_write,
    .disconnect = on_disconnect,
  };
  i2c_init(&cfg);
}
