# OptiSender

A bridge that reads swing data from an OptiShot 2 mat and forwards calculated ball-flight telemetry to a golf simulator.

## Language

**Simulator**:
A golf game application that receives shot data from OptiSender and renders the shot (e.g. Muni, OpenGolfSim).
_Avoid_: Sim UI, game, front-end

**Open Connect**:
The shared wire protocol (v1) through which a **Simulator** receives launch-monitor shot data and reports the selected club back. Originated by GSPro and adopted by other simulators.
_Avoid_: GSPro Connect, GSPro protocol, OpenCon

**MuniGolf**:
A **Simulator** that OptiSender connects to using **Open Connect**, through MuniGolf's **Relay** on the same PC. The game itself may run on another device (e.g. an iPad).
_Avoid_: Muni

**Relay**:
The part of MuniGolf that listens for **Open Connect** clients on the PC and passes their shots on to the game.
_Avoid_: Listener

**OpenGolfSim API**:
OpenGolfSim's own, separate protocol. Not **Open Connect**.
_Avoid_: Open Connect (when meaning OpenGolfSim)

## Flagged ambiguities

- "GSPro" was used for the **Open Connect** protocol; GSPro is a **Simulator**, not the protocol. Resolved: the protocol is **Open Connect**.
