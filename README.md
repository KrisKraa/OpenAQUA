# OpenAQUA
🌊 Modular Water System Controller (ESP32 + CAN)

This project is a modular, scalable water system controller built around the ESP32-S3 and a CAN-based expansion architecture. It is designed to monitor and control parameters like pH, TDS, temperature, and leaks, while supporting future expansion modules such as power strips, fleece rollers, and more.

🚀 Why this project exists

Most existing aquarium/reef controllers are:

- expensive
- closed ecosystems
- difficult to expand or customize

I started this project to create a more affordable, open, and expandable system that is not limited to reef tanks, but can also be used for:

- freshwater aquariums
- ponds
- water tanks
- breeding systems
- general water management setups

The goal is a flexible platform where you can build exactly the system you need.

🧠 System Architecture

The system is split into:

🔹 Main Controller (this board)
- ESP32-S3 (WiFi + processing)
Handles:
- sensor processing (pH, TDS, temperature, leak detection)
- system logic & automation
- user interface (display)
- CAN bus coordination

🔹 Expansion Modules (over CAN bus)

Each module has its own microcontroller and handles:

- local processing
- real-time control
- safety handling

Examples:

- power strip (relay control)
- fleece roller controller
- dosing system
- future sensor modules

🔌 Features (current hardware)

⚡ Power System
- USB-C Power Delivery input (PD)
- Up to ~20V negotiated input
Onboard conversion:
- 20V → 5V (buck)
- 5V → 3.3V (LDO)

🌐 Communication
- CAN bus (via SN65HVD230)
- 2x USB-C module ports (custom CAN + power)
- Designed for daisy-chaining modules

🧪 Sensors
- pH interface using LMP91200 (high impedance front-end)
 TDS input (ADC via ADS1115)
- Temperature sensor input
- 2x leak detection inputs

📊 ADC
- ADS1115 (I²C, high resolution)
- Used for pH and TDS measurements

🧠 MCU
- ESP32-S3-WROOM
Handles:
- WiFi
- CAN communication
- sensor processing
UI

🖥️ UI (planned)
- Small SPI display (FPC ribbon)
Status display:
- probe readings
- module status
- system alerts

🔘 Inputs
- RGB button (status + interaction)

🔧 Design Philosophy
- Modular first → everything expandable via CAN
- Local processing → modules handle their own logic
- Main controller = brain → coordination + UI + automation
- Fail-safe design → modules operate safely even if disconnected
- Low cost → uses widely available components
- Open & customizable

📡 CAN Bus Design
- Single shared CAN bus
- Multiple modules connected in parallel
Each module:
- has unique ID
- sends status + heartbeat
- receives commands
- Main controller:
- coordinates all modules
- logs and displays data

📈 Current Progress

✅ Completed
- Full power architecture (USB-C PD → 5V → 3.3V)
- ESP32 integration
- CAN bus with dual ports
- Sensor interfaces (pH, TDS, temp, leak)
- ADC integration (ADS1115)
- Modular system architecture defined

🔄 In Progress
- Display integration (FPC-based TFT)
- RGB button interface
- TDS analog front-end refinement
- PCB layout

🔜 Planned
- CAN protocol definition
- Expansion modules:
- power strip
- fleece roller
- dosing systemen
- closure + mechanical integration

🎯 End Goal

A fully modular, affordable, and open water control system that can scale from:
- a single aquarium to complex multi-tank or pond systems

without being locked into proprietary ecosystems.
