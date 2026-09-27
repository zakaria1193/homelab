#!/usr/bin/env python3
"""Minimal stdlib-only Home Assistant websocket client, meant to run ON the HA host
(inside the SSH app container, where SUPERVISOR_TOKEN is set in a login shell).

Usage:
  python3 ha-ws.py get  <url_path>              # print dashboard config JSON to stdout
  python3 ha-ws.py save <url_path> <file.json>  # replace dashboard config (storage mode)

<url_path> is the dashboard url_path (e.g. dashboard-sensors), or "-" for the default one.
No third-party packages needed (HA OS SSH app ships no websocket libs).
"""
import base64, json, os, socket, struct, sys

HOST, PORT, PATH = "supervisor", 80, "/core/websocket"


def ws_connect():
    s = socket.create_connection((HOST, PORT), timeout=30)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {PATH} HTTP/1.1\r\nHost: {HOST}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
               "Sec-WebSocket-Version: 13\r\n\r\n").encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            sys.exit("websocket handshake failed: connection closed")
        buf += chunk
    head, _, rest = buf.partition(b"\r\n\r\n")
    if b" 101 " not in head.split(b"\r\n")[0]:
        sys.exit("websocket handshake failed: " + head.decode(errors="replace"))
    return s, rest


class WS:
    def __init__(self):
        self.s, self.buf = ws_connect()

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                sys.exit("websocket closed by server")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        msg = b""
        while True:
            b1, b2 = self._read(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            op = b1 & 0x0F
            if op == 8:
                sys.exit("websocket closed by server")
            if op in (9, 10):  # ping/pong: ignore
                continue
            msg += payload
            if b1 & 0x80:
                return json.loads(msg)

    def send(self, obj):
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(data)
        hdr = bytes([0x81])
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("get", "save"):
        sys.exit(__doc__)
    cmd, url_path = sys.argv[1], sys.argv[2]
    ws = WS()
    ws.recv()  # auth_required
    ws.send({"type": "auth", "access_token": os.environ["SUPERVISOR_TOKEN"]})
    if ws.recv().get("type") != "auth_ok":
        sys.exit("websocket auth failed")
    msg = {"id": 1, "type": "lovelace/config"}
    if cmd == "save":
        msg["type"] = "lovelace/config/save"
        msg["config"] = json.load(open(sys.argv[3]))
    if url_path != "-":
        msg["url_path"] = url_path
    ws.send(msg)
    while True:
        r = ws.recv()
        if r.get("id") == 1:
            break
    if not r.get("success"):
        sys.exit("error: " + json.dumps(r.get("error")))
    if cmd == "get":
        json.dump(r["result"], sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        print(f"saved lovelace config for {url_path}")


if __name__ == "__main__":
    main()
