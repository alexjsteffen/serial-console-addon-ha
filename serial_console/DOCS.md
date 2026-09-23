# Configuration and operation

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `device` | `/dev/ttyUSB0` | Serial character device; prefer `/dev/serial/by-id/...` |
| `baud` | `115200` | Standard Linux serial speed; hardware must also support it |
| `data_bits` | `8` | 5–8 bits |
| `parity` | `none` | `none`, `even`, or `odd` |
| `stop_bits` | `1` | 1 or 2 |
| `flow_control` | `none` | `none`, `hardware` (RTS/CTS), or `software` (XON/XOFF) |
| `username` | `console` | 1–64 letters, digits, dot, underscore, or hyphen |
| `password` | empty | Required: 12–128 printable ASCII characters; spaces and punctuation allowed |
| `max_clients` | `1` | 1–8 simultaneous serial clients in total; browser limit is also set to this value |
| `ttyd_title` | `Server serial console` | Fixed browser title shown by ttyd; 1–80 printable ASCII characters |
| `ttyd_terminal_type` | `xterm-256color` | TERM value reported through ttyd to the browser session |
| `ttyd_renderer_type` | `webgl` | ttyd/xterm.js renderer: `webgl`, `canvas`, or `dom` |
| `ttyd_font_size` | `0` | Browser font size in px; `0` keeps ttyd's built-in default |
| `ttyd_cursor_style` | `block` | Cursor shape: `block`, `underline`, or `bar` |
| `ttyd_theme` | `default` | ttyd theme preset: `default`, `light`, `green`, `amber`, or `high-contrast` |
| `ttyd_leave_alert` | `true` | Show ttyd's "leave page" confirmation when closing the browser tab |
| `ttyd_resize_overlay` | `true` | Show ttyd's resize overlay when the browser terminal changes size |
| `raw_tcp` | `false` | Bind serial TCP to loopback; `true` binds all container IPv4 interfaces |
| `ssl` | `false` | Enable native HTTPS/WSS in ttyd |
| `certfile` | `fullchain.pem` | Certificate filename directly inside HA's `/ssl` directory |
| `keyfile` | `privkey.pem` | Private key filename directly inside `/ssl` |

The startup validator accepts standard rates from 50 to 4,000,000 baud, including
9600, 19200, 38400, 57600, 115200, 230400 and 921600. See `BAUDS` in `app.py` for
the complete list. Unsupported values, malformed paths, missing credentials,
missing devices, and missing enabled-TLS files fail closed.

Edit values in the Configuration UI. The equivalent example below deliberately
leaves the password blank so it cannot accidentally deploy a shared password:

```yaml
device: /dev/serial/by-id/usb-YOUR_ADAPTER-if00-port0
baud: 115200
data_bits: 8
parity: none
stop_bits: 1
flow_control: none
username: console
password: ""
max_clients: 1
ttyd_title: Server serial console
ttyd_terminal_type: xterm-256color
ttyd_renderer_type: webgl
ttyd_font_size: 0
ttyd_cursor_style: block
ttyd_theme: default
ttyd_leave_alert: true
ttyd_resize_overlay: true
raw_tcp: false
ssl: false
certfile: fullchain.pem
keyfile: privkey.pem
```

Restart after saving. Internal ports remain 7681 and 2000; change external port
numbers using the app's **Network** settings, not the serial options.
The ttyd command itself stays fixed: these options only tune browser presentation,
reported terminal metadata, and ttyd's built-in UI behaviors.

Theme presets intentionally map to fixed color palettes instead of allowing
arbitrary JSON or command fragments:

- `default`: ttyd/xterm.js upstream defaults
- `light`: light background with dark text
- `green`: classic green-screen styling
- `amber`: amber-on-dark terminal styling
- `high-contrast`: black background with high-contrast white text

## TLS and authentication

Place your PEM certificate chain and matching unencrypted private key in Home
Assistant's `/ssl` directory. Set `ssl: true`, set their filenames if different,
save, and restart. Open `https://HOSTNAME:7681/` using a hostname present in the
certificate. Renew the files and restart the app to load renewed certificates.
Private keys can remain readable only by root: ttyd loads TLS before dropping
to UID/GID 65534. The `/ssl` mount is read-only.

The username/password prompt authenticates access to ttyd. Your server's own
console login is separate. This is direct browser access, not HA Ingress, so
an already logged-in Home Assistant browser still needs the ttyd credentials.
Native TLS is optional to support existing VPN and SSH-tunnel deployments;
plain HTTP exposes credentials and console contents to network observers.
Use TLS or a trusted encrypted tunnel and do not forward these ports publicly.

ttyd checks WebSocket origins, disables URL-supplied command arguments, and
executes only the fixed socat client. It cannot offer a local Pi shell through
normal terminal input. ser2net retains root for UART access; ttyd and its terminal
clients drop privileges. AppArmor remains enabled with the Supervisor default
profile, and no extra capabilities or API permissions are requested.

Home Assistant stores options, including the password, in its app data/backups.
ttyd's native `--credential` option also makes the password visible to privileged
process inspection inside the container/host. Treat HA administrators and backups
as trusted. Passwords are not printed by this launcher. There is no login rate
limiter or account lockout; this service is intended for controlled management
networks. Avoid untrusted reverse proxies; no forwarded authentication header is used.

## Using the terminal

- Press Enter to obtain a prompt. Ctrl-C passes through to the server.
- Ctrl-] disconnects the browser's socat session. Reload the page to reconnect.
- Browser tabs get the same physical console, not independent logins. With more
  than one client, output is shared and input from every client can interleave.
  Keep `max_clients: 1` for one operator. Extra clients do not evict the owner.
- Log out of the **server** before closing the browser; disconnecting the network
  does not reliably log out a physical serial session. The next operator may
  inherit that session. Logging out of ttyd's HTTP Basic auth may require closing
  the browser's private window/session because browsers cache credentials.
- The bridge is raw TCP, not Telnet/RFC2217. Binary bytes are not Telnet-escaped;
  use socat/netcat, not a Telnet client. Serial BREAK signalling and remote
  baud-rate negotiation are not provided. Ctrl-C is a byte, not a serial BREAK.
- Window resizing affects the browser PTY, not the remote serial terminal size.
  On a Linux server use `stty rows 40 cols 120` if required by your terminal.
- There is no persistent console history/boot capture. ser2net opens the adapter
  when a client connects. Connect before rebooting the server to watch its boot.
  Opening/closing some adapters toggles DTR/RTS; test your server's behaviour.

## Optional raw TCP

Two settings are required: set `raw_tcp: true`, then map internal **2000/tcp** to
your chosen external port in Network settings. Restart. Leaving the mapping
blank prevents LAN publication, but `raw_tcp: true` still allows other containers
on HA's internal network to reach the listener. Its traffic is unauthenticated
and unencrypted regardless of ttyd credentials/TLS.

On a trusted Linux/macOS client with socat, connect using:

```sh
socat STDIO,rawer,escape=0x1d TCP:HOME_ASSISTANT_IP:2000,nodelay
```

Ctrl-] exits. This client shares the same `max_clients` allowance as browsers.
Never expose port 2000 to the public internet. Raw TCP is completely unavailable
outside the container when `raw_tcp: false`, even if its port is accidentally mapped.

## SSH access

This add-on does not run an SSH server. Use an existing trusted SSH endpoint with
TCP forwarding enabled to tunnel the browser port. From your computer:

```sh
ssh -N -L 127.0.0.1:8765:HOME_ASSISTANT_IP:7681 USER@BASTION_HOST
```

Then open `http://127.0.0.1:8765/` when `ssl: false`. The SSH server must be able
to reach the HA IP. If it runs in another HA add-on, its `127.0.0.1` is a different
container: use the HA LAN IP as shown. The bastion-to-HA segment is plain HTTP
unless native TLS is enabled; keep that segment on a trusted network.
For TLS, preserve a hostname matching your certificate when accessing the tunnel.

For a terminal rather than a browser, enable raw TCP and its mapping, then:

```sh
ssh -N -L 127.0.0.1:22000:HOME_ASSISTANT_IP:2000 USER@BASTION_HOST
# In a second local terminal:
socat STDIO,rawer,escape=0x1d TCP:127.0.0.1:22000,nodelay
```

The raw port remains reachable on HA's mapped network interface; SSH forwarding
does not make that port private. Use network firewall rules/a management VLAN,
or keep raw TCP disabled and use the authenticated browser path.

## Troubleshooting and recovery

| Symptom | Check |
| --- | --- |
| App absent from store | Folder layout, YAML syntax, Supervisor logs, refresh store |
| Password startup error | Set a unique 12+ character password and save |
| Device unavailable | Check Hardware for the path; use by-id; stop another owner |
| USB unplug/replug | Reconnect adapter, then restart app so Supervisor refreshes device mappings |
| Gibberish | Match server baud, data bits, parity, stop bits and cable levels |
| No prompt | Press Enter; verify server serial redirection/getty, cable, TX/RX, flow control |
| Blank/rejected second client | Close the first session or deliberately raise `max_clients` |
| Browser connects but typing fails | Review ser2net logs for a busy/disconnected serial device |
| HTTPS startup error | Valid matching PEM cert/key in `/ssl`; correct names and readability |
| WebSocket refused via proxy | Preserve Host/Origin and WebSocket upgrade; use direct URL to diagnose |
| Ctrl-S froze output | With software flow control, send Ctrl-Q; prefer no flow control unless needed |

The parent supervises both services and exits on either one's failure; enable
Supervisor Watchdog to restart the app. Docker HEALTHCHECK checks the two live
processes and listeners. Neither health check opens the serial device or proves
the attached server is responsive. USB disappearance during an active session
may require a manual restart. No infinite auto-reconnection is performed in the
browser, avoiding unnoticed repeated connections to a rebooting target.

HA Core can restart without ending the app, but a Pi/HAOS/Supervisor restart or
network failure can interrupt management. Provide independent power/network
where needed for the desired out-of-band availability.
