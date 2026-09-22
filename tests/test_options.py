import importlib.util
from pathlib import Path
import unittest

import yaml

SPEC = importlib.util.spec_from_file_location("app", Path(__file__).resolve().parents[1] / "serial_console/app.py")
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class OptionsTests(unittest.TestCase):
    def options(self, **changes):
        return app.validate({"password": "test-password-42", **changes})

    def test_secure_defaults(self):
        opts = self.options()
        config = app.render_ser2net(opts)
        self.assertIn("tcp,127.0.0.1,2000", config)
        self.assertIn("115200n81,local,rtscts=false,xonxoff=false", config)
        self.assertIn("max-connections: 1", config)
        self.assertNotIn(opts["password"], config)

    def test_manifest_matches_runtime(self):
        root = Path(__file__).resolve().parents[1]
        manifest = yaml.safe_load((root / "serial_console/config.yaml").read_text())
        self.assertEqual(manifest["options"], app.DEFAULTS)
        self.assertEqual(set(manifest["schema"]), set(app.DEFAULTS))
        self.assertIsNone(manifest["ports"]["2000/tcp"])
        self.assertFalse(manifest["host_network"])
        self.assertTrue(manifest["apparmor"])
        self.assertEqual(manifest["arch"], ["aarch64", "armv7", "amd64"])
        self.assertIn('io.hass.version="' + manifest["version"] + '"',
                      (root / "serial_console/Dockerfile").read_text())

    def test_password_is_required(self):
        with self.assertRaises(ValueError):
            app.validate({})

    def test_device_injection_rejected(self):
        for device in ("/dev/ttyUSB0,9600", "/dev/../etc/passwd", "/dev/tty\nUSB0",
                       "/dev/$(id)", "/dev/*{secret}", "/dev/tty\"USB0"):
            with self.subTest(device=device), self.assertRaises(ValueError):
                self.options(device=device)

    def test_stable_device_path(self):
        opts = self.options(device="/dev/serial/by-id/usb-FTDI_FT232R_A123-if00-port0")
        self.assertIn(opts["device"], app.render_ser2net(opts))

    def test_strict_types_and_limits(self):
        for change in ({"baud": True}, {"raw_tcp": "false"}, {"max_clients": 0},
                       {"data_bits": 9}, {"parity": "mark"}, {"baud": 12345},
                       {"username": "a:b"}, {"password": "x" * 12 + "\n"},
                       {"certfile": "../secret"}, {"extra": 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.options(**change)

    def test_credentials_not_interpreted_as_shell(self):
        password = "$(touch /tmp/nope):' abc"
        cmd = app.ttyd_command(self.options(password=password))
        self.assertEqual(cmd[cmd.index("--credential") + 1], "console:" + password)
        self.assertNotIn("--url-arg", cmd)
        self.assertNotIn("sh", cmd)

    def test_raw_and_tls_are_explicit(self):
        opts = self.options(raw_tcp=True, ssl=True, max_clients=3)
        self.assertIn("tcp,0.0.0.0,2000", app.render_ser2net(opts))
        self.assertIn("--ssl", app.ttyd_command(opts))


if __name__ == "__main__":
    unittest.main()
