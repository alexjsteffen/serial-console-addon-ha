"""Validate options, generate ser2net YAML, and supervise both foreground services."""

import argparse
import json
import logging
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import time

LOG = logging.getLogger("serial-console")
RUNTIME = Path("/run/serial-console")
DEFAULTS = {
    "device": "/dev/ttyUSB0", "baud": 115200, "data_bits": 8,
    "parity": "none", "stop_bits": 1, "flow_control": "none",
    "username": "console", "password": "", "max_clients": 1,
    "ttyd_title": "Server serial console",
    "ttyd_terminal_type": "xterm-256color",
    "ttyd_renderer_type": "webgl",
    "ttyd_font_size": 0,
    "ttyd_cursor_style": "block",
    "ttyd_theme": "default",
    "ttyd_leave_alert": True,
    "ttyd_resize_overlay": True,
    "raw_tcp": False, "ssl": False,
    "certfile": "fullchain.pem", "keyfile": "privkey.pem",
}
# Serial speeds supported by Linux termios; hardware may support a smaller set.
BAUDS = {50, 75, 110, 134, 150, 200, 300, 600, 1200, 1800, 2400,
         4800, 9600, 19200, 38400, 57600, 115200, 230400, 460800,
         500000, 576000, 921600, 1000000, 1152000, 1500000, 2000000,
         2500000, 3000000, 3500000, 4000000}
THEME_PRESETS = {
    "light": {
        "background": "#f7fafc", "foreground": "#1a202c",
        "cursor": "#2d3748", "selectionBackground": "#cbd5e0",
    },
    "green": {
        "background": "#001b00", "foreground": "#5cff5c",
        "cursor": "#8cff8c", "selectionBackground": "#1f441f",
    },
    "amber": {
        "background": "#1f1300", "foreground": "#ffbf66",
        "cursor": "#ffd699", "selectionBackground": "#5c3b00",
    },
    "high-contrast": {
        "background": "#000000", "foreground": "#ffffff",
        "cursor": "#ffffff", "selectionBackground": "#4a5568",
    },
}


def validate(data):
    if not isinstance(data, dict):
        raise ValueError("Options must be a JSON object")
    if set(data) - set(DEFAULTS):
        raise ValueError("Unknown configuration option; see DOCS.md")
    opts = DEFAULTS | data
    for key, default in DEFAULTS.items():
        if type(opts[key]) is not type(default):
            raise ValueError(f"Invalid type for {key}")
    # A gensio connector is a mini-language. Restrict paths as well as quoting
    # YAML so commas, expansion syntax, whitespace, or quotes cannot inject it.
    device = opts["device"]
    if not re.fullmatch(r"/dev/[A-Za-z0-9_./:+-]+", device):
        raise ValueError("device must be a simple absolute /dev path")
    if any(part in {".", ".."} for part in device.split("/")):
        raise ValueError("device must not contain relative path components")
    if opts["baud"] not in BAUDS:
        raise ValueError("Unsupported baud rate; see BAUDS in app.py")
    if opts["data_bits"] not in range(5, 9) or opts["stop_bits"] not in (1, 2):
        raise ValueError("Invalid data_bits or stop_bits")
    if opts["parity"] not in ("none", "even", "odd"):
        raise ValueError("Invalid parity")
    if opts["flow_control"] not in ("none", "hardware", "software"):
        raise ValueError("Invalid flow_control")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", opts["username"]):
        raise ValueError("username must contain 1-64 letters, digits, _, . or -")
    password = opts["password"]
    if not 12 <= len(password) <= 128 or any(not 32 <= ord(c) <= 126 for c in password):
        raise ValueError("Set password to 12-128 printable ASCII characters before starting")
    if not 1 <= opts["max_clients"] <= 8:
        raise ValueError("max_clients must be between 1 and 8")
    if not 1 <= len(opts["ttyd_title"]) <= 80 or any(not 32 <= ord(c) <= 126 for c in opts["ttyd_title"]):
        raise ValueError("ttyd_title must contain 1-80 printable ASCII characters")
    if not re.fullmatch(r"[A-Za-z0-9+_.-]{1,32}", opts["ttyd_terminal_type"]):
        raise ValueError("ttyd_terminal_type must contain only letters, digits, +, _, . or -")
    if opts["ttyd_renderer_type"] not in ("webgl", "canvas", "dom"):
        raise ValueError("ttyd_renderer_type must be webgl, canvas or dom")
    if opts["ttyd_font_size"] not in (0, *range(8, 33)):
        raise ValueError("ttyd_font_size must be 0 or between 8 and 32")
    if opts["ttyd_cursor_style"] not in ("block", "underline", "bar"):
        raise ValueError("ttyd_cursor_style must be block, underline or bar")
    if opts["ttyd_theme"] != "default" and opts["ttyd_theme"] not in THEME_PRESETS:
        raise ValueError(f"ttyd_theme must be default or one of: {', '.join(THEME_PRESETS)}")
    for key in ("certfile", "keyfile"):
        if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", opts[key]):
            raise ValueError(f"{key} must be a filename directly inside /ssl")
    return opts


def render_ser2net(opts):
    host = "0.0.0.0" if opts["raw_tcp"] else "127.0.0.1"
    speed = f'{opts["baud"]}{opts["parity"][0]}{opts["data_bits"]}{opts["stop_bits"]}'
    flow = {
        "none": "rtscts=false,xonxoff=false",
        "hardware": "rtscts=true,xonxoff=false",
        "software": "rtscts=false,xonxoff=true",
    }[opts["flow_control"]]
    connector = f'serialdev,{opts["device"]},{speed},local,{flow}'
    # v1 YAML connection syntax is supported by the packaged ser2net 4.6.4.
    # There is just one connection, so no duplicate YAML mapping keys.
    return (
        "connection: &console\n"
        f"  accepter: {json.dumps(f'tcp,{host},2000')}\n"
        "  enable: on\n"
        "  timeout: 0\n"
        f"  connector: {json.dumps(connector)}\n"
        "  options:\n"
        f'    max-connections: {opts["max_clients"]}\n'
        "    kickolduser: false\n"
        "    chardelay: false\n"
    )


def ttyd_command(opts):
    # No shell, no URL-provided arguments, and no command configurable by clients.
    # ttyd drops privileges before executing its fixed TCP terminal client.
    theme = THEME_PRESETS.get(opts["ttyd_theme"])
    cmd = ["ttyd", "--port", "7681", "--interface", "0.0.0.0",
           "--credential", f'{opts["username"]}:{opts["password"]}',
           "--check-origin", "--writable", "--max-clients", str(opts["max_clients"]),
           "--uid", "65534", "--gid", "65534", "--debug", "3",
           "--terminal-type", opts["ttyd_terminal_type"],
           "--client-option", f'titleFixed={opts["ttyd_title"]}',
           "--client-option", f'rendererType={opts["ttyd_renderer_type"]}',
           "--client-option", f'cursorStyle={opts["ttyd_cursor_style"]}',
           "--client-option", "disableReconnect=true"]
    if opts["ttyd_font_size"]:
        cmd += ["--client-option", f'fontSize={opts["ttyd_font_size"]}']
    if not opts["ttyd_leave_alert"]:
        cmd += ["--client-option", "disableLeaveAlert=true"]
    if not opts["ttyd_resize_overlay"]:
        cmd += ["--client-option", "disableResizeOverlay=true"]
    if theme:
        cmd += ["--client-option", f'theme={json.dumps(theme, separators=(",", ":"))}']
    if opts["ssl"]:
        cmd += ["--ssl", "--ssl-cert", f'/ssl/{opts["certfile"]}',
               "--ssl-key", f'/ssl/{opts["keyfile"]}']
    return cmd + ["socat", "STDIO,rawer,escape=0x1d", "TCP:127.0.0.1:2000,nodelay"]


def is_listening(port):
    # Checking the kernel table does not connect to ser2net (which could toggle
    # the adapter's DTR line and interrupt the server on each health probe).
    for name in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            rows = Path(name).read_text().splitlines()[1:]
        except FileNotFoundError:
            continue
        for row in rows:
            fields = row.split()
            if int(fields[1].split(":")[1], 16) == port and fields[3] == "0A":
                return True
    return False


def preflight(opts):
    try:
        mode = os.stat(opts["device"]).st_mode
    except OSError as exc:
        raise ValueError("Serial device unavailable; check Hardware and restart after reconnecting USB") from exc
    if not stat.S_ISCHR(mode):
        raise ValueError("device must resolve to a character device")
    if not os.access(opts["device"], os.R_OK | os.W_OK):
        raise ValueError("Serial device is not readable/writable")
    if opts["ssl"]:
        for key in ("certfile", "keyfile"):
            path = Path("/ssl") / opts[key]
            if not path.is_file() or not os.access(path, os.R_OK):
                raise ValueError(f"TLS {key} is missing or unreadable in /ssl")
    for port in (2000, 7681):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
            except OSError as exc:
                raise ValueError(f"Port {port} is already in use") from exc


def stop_children(children):
    # Each service owns a process group; ttyd also terminates its PTY clients.
    for child in children:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 8
    for child in children:
        try:
            child.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()


def serve(opts):
    preflight(opts)
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    config = RUNTIME / "ser2net.yaml"
    config.write_text(render_ser2net(opts))
    children = []
    stopping = False

    def shutdown(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        LOG.info("Starting serial console: %s at %s baud", opts["device"], opts["baud"])
        if opts["raw_tcp"]:
            LOG.warning("Raw TCP is unauthenticated; publish port 2000 only on a trusted LAN/VPN")
        if not opts["ssl"]:
            LOG.warning("Browser transport is HTTP; use a trusted VPN/SSH tunnel or enable ssl")
        # -d keeps ser2net in the foreground and sends diagnostics to stderr.
        children.append(subprocess.Popen(["ser2net", "-d", "-c", str(config)], start_new_session=True))
        deadline = time.monotonic() + 10
        while not stopping:
            if children[0].poll() is not None:
                raise RuntimeError("ser2net exited during startup; check diagnostics above")
            if is_listening(2000):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("ser2net did not open its listener within 10 seconds")
            time.sleep(0.1)
        if stopping:
            return 0
        children.append(subprocess.Popen(ttyd_command(opts), start_new_session=True))
        (RUNTIME / "pids.json").write_text(json.dumps([p.pid for p in children]))
        while not stopping:
            for index, child in enumerate(children):
                if child.poll() is not None:
                    name = ("ser2net", "ttyd")[index]
                    raise RuntimeError(f"{name} exited unexpectedly (status {child.returncode})")
            time.sleep(0.25)
        return 0
    finally:
        stop_children(children)
        (RUNTIME / "pids.json").unlink(missing_ok=True)


def healthcheck():
    try:
        pids = json.loads((RUNTIME / "pids.json").read_text())
        if len(pids) != 2:
            return 1
        for pid in pids:
            os.kill(pid, 0)
        return 0 if all(is_listening(p) for p in (2000, 7681)) else 1
    except (OSError, ValueError, TypeError):
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--options", type=Path, default=Path("/data/options.json"))
    parser.add_argument("--render", action="store_true", help="Validate options and print ser2net YAML only")
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    if args.healthcheck:
        return healthcheck()
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        opts = validate(json.loads(args.options.read_text()))
        if args.render:
            print(render_ser2net(opts), end="")
            return 0
        return serve(opts)
    except (OSError, ValueError, RuntimeError) as exc:
        # Never dump options, credentials, or a subprocess argument list.
        LOG.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
