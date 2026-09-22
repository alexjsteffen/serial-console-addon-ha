# Serial Console

Expose a server serial console through ser2net and an authenticated ttyd browser
terminal. Defaults to `/dev/ttyUSB0` at 115200 8N1 with no flow control.

Set a unique password before starting. Prefer the adapter's `/dev/serial/by-id/`
path. Browser port: 7681. Raw TCP port 2000 is disabled by default.

Read the **Documentation** tab ([DOCS.md](DOCS.md)) for configuration and secure
access. Local installation instructions are in the repository's root README.
