# Validation record

Validated on **2026-09-22**.

## Runtime and syntax validation completed

Actual executables were tested in an isolated Alpine 3.23.6 x86-64 filesystem
under Linux (WSL), with a real kernel pseudo-terminal representing the server's
serial port. This was not just YAML parsing or mocked subprocess testing.

| Package | Version tested |
| --- | --- |
| ser2net | 4.6.4-r0 |
| gensio-libs | 2.8.14-r0 |
| ttyd | 1.7.7-r0 |
| socat | 1.8.1.3-r0 |
| Python | 3.12.14-r0 |

Passed:

- ShellCheck on `run.sh`.
- Eight unit tests, including credential/path injection rejection, strict types,
  required password, safe defaults and manifest/runtime consistency.
- Twelve configurations accepted by the actual ser2net/gensio parser, covering
  every offered parity, flow-control, data-bit and stop-bit option independently.
  These prove parser acceptance; only 115200 8N1 was used for byte-transfer tests.
- Real two-way TCP-to-PTY byte transport, including Ctrl-C, NUL and `0xff`.
- Default single-client enforcement and two-client output broadcasting.
- Missing/wrong HTTP credentials rejected; correct credentials accepted.
- Unauthenticated and cross-origin WebSocket connections rejected.
- Authenticated WebSocket terminal input/output through ttyd and socat; Ctrl-C
  reaches the simulated server instead of terminating the local client.
- Native HTTPS/WSS, including TLS files readable only by root and ttyd dropping
  privileges before running the terminal client.
- Missing password/device/TLS configuration fails before opening service ports.
- Graceful shutdown releases listeners; killed ser2net causes the parent to fail
  and stop ttyd. Test logs contain no configured password.
- Signed Alpine package indexes resolve the complete production dependency set
  on **aarch64, armv7, and x86_64**. Architecture-specific official root filesystems
  were SHA-256 checked and their signing keys used; signature checking was not disabled.

## Why this ser2net syntax is valid

The generated configuration uses ser2net's YAML `connection: &console` form,
not the obsolete colon-delimited ser2net 3.x format. There is one connection,
so the document has no duplicate top-level keys. For default options:

```yaml
connection: &console
  accepter: "tcp,127.0.0.1,2000"
  enable: on
  timeout: 0
  connector: "serialdev,/dev/ttyUSB0,115200n81,local,rtscts=false,xonxoff=false"
  options:
    max-connections: 1
    kickolduser: false
    chardelay: false
```

`local` ignores modem carrier control; flow control is explicitly disabled.
The raw TCP accepter and socat client use the same protocol. ttyd 1.7.7 needs
`--writable` for keyboard input; it is enabled explicitly.

The packaged ser2net does not offer a standalone validation-only command.
Tests launch it in the foreground using `-d -c`, require its listener to open,
then exercise serial transport. Merely checking that its process remains alive
would be insufficient because a configuration failure can leave a process running.

The syntax and flags were checked against the upstream
[ser2net manual](https://github.com/cminyard/ser2net/blob/master/ser2net.yaml.5),
[gensio manual](https://github.com/cminyard/gensio/blob/master/man/gensio.5), and
[ttyd 1.7.7 manual](https://github.com/tsl0922/ttyd/blob/1.7.7/man/ttyd.man.md).

## Home Assistant compatibility review

The manifest was reviewed against current
[Home Assistant app documentation](https://developers.home-assistant.io/docs/apps/configuration/)
and the [Supervisor schema source](https://github.com/home-assistant/supervisor/blob/main/supervisor/apps/validate.py).
Current Supervisor accepts legacy architecture names via `ARCH_ALL_COMPAT`
while warning that armv7 is deprecated. This review is not an actual Supervisor
installation test. `repository.yaml` omits optional URL/contact details until a
real remote repository and maintainer contact are chosen.

## Remaining deployment checks

No Docker engine, physical Pi, USB adapter or running HAOS installation was
available for this work. The following have **not** been claimed as tested:

- Docker image build/entrypoint and Home Assistant installation/AppArmor/device mapping.
- Running binaries on aarch64 or armv7 hardware/emulation. The included CI workflow
  builds and runs the suite on all three platforms when hosted on GitHub.
- Real USB unplug/replug, device by-id resolution inside Supervisor, DTR/RTS effects,
  electrical cable compatibility, and hardware flow control.
- Long-running stability, recovery across HAOS reboots, and physical server boot output.

Before relying on this for management, install on the Pi, confirm the by-id path,
test login and Ctrl-C, reboot the **server** while connected, reconnect the USB
adapter and restart the app, and verify that raw port 2000 is unreachable with
default settings. Confirm HTTPS or your tunnel and recovery after a Pi restart.
Keep another way to reach the server during this first hardware qualification.
