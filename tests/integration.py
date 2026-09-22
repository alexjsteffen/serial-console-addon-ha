"""Linux-only end-to-end test against a PTY, real ser2net, ttyd and WebSockets.

Run as root in an isolated container/chroot; ports 2000 and 7681 must be free.
Dependencies: production packages plus py3-websocket-client.
"""
import base64
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import signal
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import websocket

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("app", ROOT / "serial_console/app.py")
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)
PASSWORD = "integration-only-password"
AUTH = "Basic " + base64.b64encode(f"console:{PASSWORD}".encode()).decode()


def wait_for(predicate, description, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError(f"Timed out: {description}")


def read_fd(fd, expected):
    data = b""
    deadline = time.monotonic() + 5
    while len(data) < len(expected) and time.monotonic() < deadline:
        if select.select([fd], [], [], 0.2)[0]:
            data += os.read(fd, 4096)
    assert data == expected, (data, expected)


def read_socket(sock, expected):
    data = b""
    while len(data) < len(expected):
        chunk = sock.recv(4096)
        assert chunk, "Socket closed before expected output"
        data += chunk
    assert data == expected, (data, expected)


def http_status(auth=None, secure=False):
    req = urllib.request.Request(("https" if secure else "http") + "://127.0.0.1:7681/")
    if auth:
        req.add_header("Authorization", auth)
    try:
        with urllib.request.urlopen(req, timeout=3, context=ssl._create_unverified_context() if secure else None) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_native_configuration_variants():
    # Exercise the native gensio parser, not just a generic YAML loader.
    master, slave = pty.openpty()
    variants = [{"flow_control": value} for value in ("none", "hardware", "software")]
    variants += [{"parity": value} for value in ("none", "even", "odd")]
    variants += [{"data_bits": value} for value in (5, 6, 7, 8)]
    variants += [{"stop_bits": value} for value in (1, 2)]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for variant in variants:
                opts = app.validate({"device": os.ttyname(slave), "password": PASSWORD, **variant})
                config = Path(tmp) / "serial.yaml"
                config.write_text(app.render_ser2net(opts))
                with (Path(tmp) / "log").open("w+") as log:
                    process = subprocess.Popen(["ser2net", "-d", "-c", str(config)], stdout=log, stderr=log)
                    try:
                        wait_for(lambda: process.poll() is not None or app.is_listening(2000), "native config parser")
                        assert process.poll() is None, variant
                        # ser2net can stay alive after a configuration error; require a listener.
                        assert app.is_listening(2000), variant
                    finally:
                        process.terminate()
                        process.wait(timeout=5)
                    log.seek(0)
                    assert not log.read(), variant
    finally:
        os.close(master)
        os.close(slave)


def test_fail_closed():
    with tempfile.TemporaryDirectory() as tmp:
        options = Path(tmp) / "options.json"
        for changes in ({"password": ""}, {"device": "/dev/does-not-exist"},
                        {"ssl": True, "device": "/dev/null", "keyfile": "missing-test-key.pem"}):
            options.write_text(json.dumps({"password": PASSWORD, **changes}))
            result = subprocess.run(["python3", str(ROOT / "serial_console/app.py"), "--options", str(options)],
                                    capture_output=True, timeout=5)
            assert result.returncode == 1
            assert PASSWORD.encode() not in result.stderr
            assert not app.is_listening(2000) and not app.is_listening(7681)


def run_case(raw=False, secure=False, fail_service=False, max_clients=1, tls_files=None):
    master, slave = pty.openpty()
    process = None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            options = Path(tmp) / "options.json"
            settings = {"device": os.ttyname(slave), "password": PASSWORD,
                        "raw_tcp": raw, "ssl": secure, "max_clients": max_clients}
            if tls_files:
                settings.update(certfile=tls_files[0], keyfile=tls_files[1])
            options.write_text(json.dumps(settings))
            logfile = Path(tmp) / "service.log"
            with logfile.open("w") as log:
                command = (["/sbin/tini", "--", "/app/run.sh"] if Path("/app/run.sh").exists()
                           else ["python3", str(ROOT / "serial_console/app.py")])
                process = subprocess.Popen(command + ["--options", str(options)],
                                           stdout=log, stderr=log)
                try:
                    wait_for(lambda: app.healthcheck() == 0, "service startup")
                    assert http_status(secure=secure) == 401
                    assert http_status("Basic YmFkOmJhZA==", secure=secure) == 401
                    assert http_status(AUTH, secure=secure) == 200
                    # Raw bytes (including NUL and IAC) survive in both directions.
                    with socket.create_connection(("127.0.0.1", 2000), timeout=3) as first:
                        first.sendall(b"hello\x03\x00\xff\r")
                        read_fd(master, b"hello\x03\x00\xff\r")
                        with socket.create_connection(("127.0.0.1", 2000), timeout=3) as second:
                            second.sendall(b"second\r")
                            if max_clients > 1:
                                read_fd(master, b"second\r")
                            else:
                                assert not select.select([master], [], [], 0.3)[0], "Excess client wrote to serial"
                            os.write(master, b"boot\r\n\xff\x00")
                            read_socket(first, b"boot\r\n\xff\x00")
                            if max_clients > 1:
                                read_socket(second, b"boot\r\n\xff\x00")
                    time.sleep(0.3)
                    scheme = "wss" if secure else "ws"
                    origin = ("https" if secure else "http") + "://127.0.0.1:7681"
                    url = f"{scheme}://127.0.0.1:7681/ws"
                    for headers, bad_origin in (([], origin), (["Authorization: " + AUTH], "https://evil.invalid")):
                        try:
                            ws = websocket.create_connection(url, header=headers, origin=bad_origin, subprotocols=["tty"],
                                                             timeout=3, sslopt={"cert_reqs": ssl.CERT_NONE})
                        except (websocket.WebSocketBadStatusException, websocket.WebSocketConnectionClosedException):
                            pass
                        else:
                            ws.close()
                            raise AssertionError("WebSocket authentication/origin check bypassed")
                    # ttyd's WebSocket protocol: initial JSON, then '0' input/output.
                    ws = websocket.create_connection(url, header=["Authorization: " + AUTH], origin=origin,
                                                     subprotocols=["tty"], timeout=5,
                                                     sslopt={"cert_reqs": ssl.CERT_NONE})
                    try:
                        ws.send(json.dumps({"AuthToken": base64.b64encode(f"console:{PASSWORD}".encode()).decode(),
                                            "columns": 80, "rows": 24}))
                        time.sleep(0.3)
                        ws.send_binary(b"0browser\x03\r")
                        read_fd(master, b"browser\x03\r")
                        os.write(master, b"server-reply\r\n")
                        output = b""
                        while b"server-reply\r\n" not in output:
                            msg = ws.recv()
                            assert msg, "WebSocket closed before serial reply"
                            if isinstance(msg, str):
                                msg = msg.encode()
                            if msg.startswith(b"0"):
                                output += msg[1:]
                    finally:
                        ws.close()
                    if fail_service:
                        pid = json.loads((app.RUNTIME / "pids.json").read_text())[0]
                        os.kill(pid, signal.SIGKILL)
                        assert process.wait(timeout=12) == 1
                    else:
                        process.terminate()
                        assert process.wait(timeout=12) == 0
                    assert app.healthcheck() == 1
                    wait_for(lambda: not app.is_listening(2000) and not app.is_listening(7681), "listener cleanup")
                    assert PASSWORD not in logfile.read_text(), "Credentials leaked in logs"
                except BaseException:
                    print(logfile.read_text())
                    raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=12)
        os.close(master)
        os.close(slave)


if __name__ == "__main__":
    test_native_configuration_variants()
    print("PASS: native ser2net parser accepts all 12 serial option variants")
    test_fail_closed()
    print("PASS: invalid password, missing device and missing TLS files fail closed")
    run_case()
    print("PASS: HTTP auth, WebSocket auth/origin, bidirectional serial, exclusive client, Ctrl-C, shutdown")
    run_case(raw=True, fail_service=True, max_clients=2)
    print("PASS: raw TCP enabled, shared clients, failure propagation and sibling cleanup")
    Path("/ssl").mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir="/ssl", prefix="test-cert-", suffix=".pem") as cert:
        with tempfile.NamedTemporaryFile(dir="/ssl", prefix="test-key-", suffix=".pem") as key:
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                            "-subj", "/CN=localhost", "-keyout", key.name, "-out", cert.name],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            run_case(secure=True, tls_files=(Path(cert.name).name, Path(key.name).name))
    print("PASS: HTTPS/WSS with root-readable TLS private key and unprivileged ttyd")
