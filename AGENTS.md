# Project guidance

This repository is a Home Assistant OS local add-on for a physical server console.

- Keep `serial_console/config.yaml` as the only file named config.yaml.
- Keep passwords mandatory, raw TCP disabled by default, and ttyd's command fixed.
- Never pass user input through a shell or permit gensio/YAML injection.
- Only ser2net may open the serial device. Do not probe it from a health check.
- Preserve AppArmor and protection mode; do not request broad hardware/API access.
- Match version fields in config.yaml and Dockerfile when shipping updates.
- Use Linux LF line endings and no actual credentials in fixtures or commits.
- Run ShellCheck, unit tests and PTY integration tests as documented in README.md.
- Validate configuration with the actual ser2net binary; parsing YAML alone is insufficient.
- Distinguish simulated-serial tests from real HAOS/hardware qualification.
- Keep armv7 documented as legacy; recommend aarch64 on Raspberry Pi 4.
