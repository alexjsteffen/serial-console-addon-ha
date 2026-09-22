# Changelog

## 1.0.0

- Configurable serial console with 115200 8N1 defaults and stable by-id paths.
- Password-protected ttyd, optional native TLS, origin checks, fixed unprivileged client.
- ser2net raw TCP remains loopback-only unless explicitly enabled.
- Supervised service lifecycle, non-invasive health checks, and automated PTY tests.
- Multi-platform Dockerfile for aarch64, amd64, and legacy armv7.
