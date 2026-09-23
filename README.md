# Serial Console for Home Assistant OS

A local Home Assistant add-on (now called an **app**) for out-of-band access to a
server's physical serial console. Defaults: `/dev/ttyUSB0`, **115200 baud, 8N1,
no flow control**, one client, authenticated browser terminal on port **7681**.
Prefer the adapter's stable `/dev/serial/by-id/...` path.

```text
Server console <-> USB serial adapter <-> ser2net <-> socat <-> ttyd <-> browser
                                         |
                                         +--> optional raw TCP port 2000
```

Only ser2net opens the serial device. ttyd runs a fixed TCP client, not a shell.
The service starts before Home Assistant Core and does not depend on Core's API.
It still depends on the Pi, HAOS/Supervisor, power, and network being available.
This repository was vibe coded, then tightened with explicit validation, docs,
and PTY-backed integration tests.

## Install locally on your Pi 4

1. Use **64-bit Home Assistant OS** on the Pi 4. Plug in the correct serial adapter
   and ensure the server console also uses 115200 8N1. USB TTL and RS-232 adapters
   have different electrical levels; use the type required by the server.
2. Copy the **`serial_console` folder** from this repository into Home Assistant's
   `/addons` folder. With the Samba app, open `\\homeassistant.local\addons` from
   Windows and copy it there. With an SSH/editor app that exposes `/addons`, use
   that directory. The result must include `/addons/serial_console/config.yaml`
   and `/addons/serial_console/Dockerfile`. Do not put it in `/config` or HACS.
3. Open **Settings → Apps → App store → ⋮ → Check for updates**. Older Home
   Assistant versions label these **Add-ons**, **Add-on store**, and **Local add-ons**.
   Refresh the page, find **Serial Console** under **Local apps**, and install it.
   The image builds on the Pi; internet access to the image/package registries is
   required on first installation and rebuilds.
4. Open its **Configuration** tab. Select the serial adapter (find its by-id path
   under **Settings → System → Hardware → All hardware**). Set `password` to a
   unique password of 12–128 printable ASCII characters. There is deliberately
   no usable default password: startup fails until you supply one.
5. Keep `raw_tcp: false` and the Network mapping for port 2000 blank. Save and
   start. Inspect **Logs**, then choose **Open Web UI** (or pin it to the HA
   sidebar from the app's Info tab), or open
   `http://HOME_ASSISTANT_IP:7681/`. Log in as `console` with your configured password.
   Press Enter once to request the server's login prompt.
6. Enable **Start on boot** and **Watchdog** on the app's Info tab. For normal
   deployment, enable TLS as described below or reach it through a trusted VPN/
   SSH tunnel. Basic authentication over plain HTTP does not encrypt credentials.

No Protection mode change, host networking, Docker API, or Supervisor API access
is needed. UART access maps serial devices into the container; the selected device
must not simultaneously be used by another add-on/integration.

See [configuration and operations](serial_console/DOCS.md) for TLS, SSH tunnelling,
optional raw TCP, ttyd presentation/design options, troubleshooting, and every
option.

## Architectures

| Home Assistant | Docker platform | Status |
| --- | --- | --- |
| aarch64 | linux/arm64 | Intended platform for Pi 4 with 64-bit HAOS |
| amd64 | linux/amd64 | Intended platform for x86-64 HAOS |
| armv7 | linux/arm/v7 | Legacy build compatibility only |

Home Assistant ended official 32-bit support in 2025.12. Including armv7 here
cannot restore upstream support or updates; migrate the Pi 4 to aarch64 for
production. [Home Assistant architecture policy](https://www.home-assistant.io/more-info/unsupported/system_architecture/).

## Repository contents

- `serial_console/`: installable add-on, Dockerfile, launcher, documentation.
- `tests/`: option validation plus real PTY/ser2net/ttyd/WebSocket integration tests.
- `.github/workflows/ci.yaml`: Docker build and integration tests on all three platforms.
- `repository.yaml`: metadata for adding this as a Git-hosted app repository later.
- [VALIDATION.md](VALIDATION.md): actual test results and remaining hardware checks.
- [AGENTS.md](AGENTS.md): project guidance for future Codex work.

This is a local Git project; no remote repository or image has been published.
If you publish it, put this repository's files at the Git root, set your real
homepage and maintainer in `repository.yaml`, and optionally set `url` in the
add-on's `config.yaml`. Users can then add that Git URL in the app store's
Repositories menu. No placeholder image URL is configured: Supervisor builds
the Dockerfile locally. A separate `build.yaml` is not required by the current
[Home Assistant build workflow](https://developers.home-assistant.io/blog/2026/04/02/builder-migration/).

## Develop and test

From the repository root on a machine with Linux Docker:

```sh
docker build -t serial-console:dev ./serial_console
docker run --rm --entrypoint /bin/sh \
  -v "$PWD:/project:ro" serial-console:dev -ec \
  'apk add --no-cache py3-websocket-client py3-yaml openssl shellcheck;
   cd /project;
   shellcheck serial_console/run.sh;
   python3 -m unittest discover -s tests -p "test_*.py" -v;
   python3 tests/integration.py'
```

The test container needs no physical device, host ports, host network, or
privileged mode. It uses a pseudo-terminal inside its own namespace. Test TLS
certificates are generated only inside that disposable container.

To test with actual hardware, create a private `options.json` using the options
from `serial_console/config.yaml` and your own password. Map your chosen adapter:

```sh
docker run --rm --name serial-console \
  --device /dev/serial/by-id/YOUR_ADAPTER:/dev/ttyUSB0 \
  -v "$PWD/options.json:/data/options.json:ro" \
  -p 127.0.0.1:7681:7681 serial-console:dev
```

Use `/dev/ttyUSB0` in this Docker example's options because that is the mapped
container path. For TLS add `-v /path/to/certificates:/ssl:ro` and set `ssl: true`.
The example publishes only to the Docker host's loopback; use a local browser
or an SSH tunnel. Do not commit options or TLS keys.

Alpine is fixed at 3.23.6; ser2net is constrained to 4.6.4 and ttyd to 1.7.7,
allowing Alpine package security revisions. Builds are not bit-for-bit reproducible
because maintained package revisions can change. CI logs installed versions.
Rebuild regularly for security updates; review new upstream application versions
and rerun the integration suite before changing constraints.

After local edits, bump `version` in `config.yaml` and the Docker label, refresh
the app store and install the update. Save options/backups first. Changes to
runtime options require a restart; changes to code require an image rebuild.

## Upstream references

- [Local app installation](https://developers.home-assistant.io/docs/apps/tutorial/)
- [Home Assistant app configuration](https://developers.home-assistant.io/docs/apps/configuration/)
- [ser2net configuration manual](https://github.com/cminyard/ser2net/blob/master/ser2net.yaml.5)
- [gensio connector options](https://github.com/cminyard/gensio/blob/master/man/gensio.5)
- [ttyd 1.7.7 command options](https://github.com/tsl0922/ttyd/blob/1.7.7/man/ttyd.man.md)

MIT license for this project's original code. Bundled distribution packages
retain their respective upstream licenses.
