# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-04-05

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings

- **Project:** talos-argocd-proxmox — Production GitOps K8s cluster on Talos OS with self-managing ArgoCD
- **Epever MPPT RS485**: The Exar XR21B1411 USB adapter requires `RS485 RTS_AFTER_SEND` (not RTS_ON_SEND) via kernel ioctl. The built-in `xr_serial` driver on kernel 6.12 supports RS485 natively.
- **USB device stability**: Always use `/dev/serial/by-id/` paths for Docker device mapping — ttyUSB numbering changes on unplug/replug/reboot.
- **RPi4 solar monitor**: Docker container at `192.168.10.174` running `epever-solar` with FastAPI + pymodbus. Prometheus scrapes :9812, Swagger UI at :8080/docs.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->
- [2026-04-08] Epever RS485 adapter: used `serial.rs485.RS485Settings(rts_level_for_tx=True)` and kernel default `RTS_ON_SEND` — both wrong. Must use kernel ioctl with `SER_RS485_RTS_AFTER_SEND` flag. Always test both polarities when RS485 doesn't respond.
- [2026-04-08] pymodbus 3.9.x: `read_input_registers(addr, count)` fails — `count` is keyword-only. Use `read_input_registers(addr, count=count, slave=unit)`.
- [2026-04-08] Epever MPPT voltage registers (0x9003-0x900E): single `write_register` (func 0x06) returns exception code 4. Must use `write_registers` (func 0x10) to batch-write all 12 at once. Non-voltage registers like battery_capacity and temp_coeff accept single writes fine.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->