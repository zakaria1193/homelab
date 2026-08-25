"""Minimal WebSocket + PTY bridge for the cockpit's per-service shells.

Standard library only, matching the rest of this service: the WebSocket
handshake and framing are implemented here rather than pulled from a package.

A terminal is always bound server-side to one services.conf entry - the client
picks a service name, never a command - and the shell is launched either in that
service's directory or inside its container.
"""

import base64
import errno
import fcntl
import hashlib
import json
import os
import pty
import select
import signal
import socket
import struct
import subprocess
import termios
import time

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT, OP_TEXT, OP_BINARY = 0x0, 0x1, 0x2
OP_CLOSE, OP_PING, OP_PONG = 0x8, 0x9, 0xA

READ_SIZE = 65536


# --------------------------------------------------------------------------- #
# WebSocket framing
# --------------------------------------------------------------------------- #
def accept_key(client_key):
    digest = hashlib.sha1((client_key + GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def encode_frame(payload, opcode=OP_BINARY):
    """Server -> client frame (never masked)."""
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header += struct.pack(">H", length)
    else:
        header.append(127)
        header += struct.pack(">Q", length)
    return bytes(header) + payload


class FrameReader:
    """Incremental client -> server frame parser (handles masking + fragments)."""

    def __init__(self):
        self.buffer = bytearray()
        self._fragments = bytearray()
        self._fragment_op = None

    def feed(self, data):
        self.buffer += data

    def frames(self):
        """Yield (opcode, payload) for every complete frame buffered so far."""
        while True:
            frame = self._next_frame()
            if frame is None:
                return
            opcode, payload, final = frame

            if opcode == OP_CONT:
                self._fragments += payload
                if final:
                    complete = (self._fragment_op or OP_BINARY, bytes(self._fragments))
                    self._fragments = bytearray()
                    self._fragment_op = None
                    yield complete
                continue

            if opcode in (OP_TEXT, OP_BINARY) and not final:
                self._fragment_op = opcode
                self._fragments = bytearray(payload)
                continue

            yield opcode, payload

    def _next_frame(self):
        buf = self.buffer
        if len(buf) < 2:
            return None

        final = bool(buf[0] & 0x80)
        opcode = buf[0] & 0x0F
        masked = bool(buf[1] & 0x80)
        length = buf[1] & 0x7F
        offset = 2

        if length == 126:
            if len(buf) < offset + 2:
                return None
            length = struct.unpack(">H", buf[offset:offset + 2])[0]
            offset += 2
        elif length == 127:
            if len(buf) < offset + 8:
                return None
            length = struct.unpack(">Q", buf[offset:offset + 8])[0]
            offset += 8

        mask = b""
        if masked:
            if len(buf) < offset + 4:
                return None
            mask = bytes(buf[offset:offset + 4])
            offset += 4

        if len(buf) < offset + length:
            return None

        payload = bytes(buf[offset:offset + length])
        del self.buffer[:offset + length]

        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload, final


# --------------------------------------------------------------------------- #
# Shell construction
# --------------------------------------------------------------------------- #
import tmux_manager

CONTAINER_SHELL = "command -v bash >/dev/null 2>&1 && exec bash || exec sh"


def build_command(check, working_dir, login_shell, where="auto", session=None):
    """Return (argv, cwd, label, init) for a service's shell or tmux session.

    `where` picks the target for containers: "container" (the default for
    type = docker) execs inside it, "host" opens a shell next to its
    docker-compose.yml instead. Everything else always runs on the host.

    If `session` is specified, attaches directly to that named tmux session.
    Otherwise, if tmux is available, attaches to/creates a persistent named tmux
    session with `STATUS_TMUX_PREFIX` for the requested service.
    """
    if session:
        session_name = tmux_manager.sanitize_name(session)
        if not session_name.startswith(tmux_manager.TMUX_PREFIX):
            session_name = "%s%s" % (tmux_manager.TMUX_PREFIX, session_name)
        if tmux_manager.is_available():
            target_cwd = working_dir if (working_dir and os.path.isdir(working_dir)) else os.path.expanduser("~")
            tmux_manager.ensure_session(
                session_name, cwd=target_cwd, inner_argv=[login_shell, "-l"]
            )
            argv = ["tmux", "-u", "attach-session", "-t", session_name]
            label = "tmux attach -t %s" % session_name
            return argv, target_cwd, label, ""
        return [login_shell, "-l"], working_dir, "%s in %s" % (login_shell, working_dir), ""

    if check and check.get("type") == "docker" and where != "host":
        container = check["container"]
        raw_argv = [
            "docker", "exec", "-it",
            "-e", "TERM=xterm-256color",
            container, "sh", "-c", CONTAINER_SHELL,
        ]
        raw_cwd = None
        raw_label = "docker exec -it %s" % container
        raw_init = ""
    else:
        command = check.get("command", "") if check else ""
        if command:
            raw_init = command + "\n"
            raw_label = "%s in %s" % (command, working_dir)
        elif working_dir and os.path.isfile(os.path.join(working_dir, "Makefile")):
            raw_init = "make help\n"
            raw_label = "%s in %s" % (login_shell, working_dir)
        elif working_dir and os.path.isfile(os.path.join(working_dir, "docker-compose.yml")):
            # A compose directory has no `make help`; show the stack instead.
            raw_init = "docker compose ps\n"
            raw_label = "%s in %s" % (login_shell, working_dir)
        else:
            raw_init = ""
            raw_label = "%s in %s" % (login_shell, working_dir)
        raw_argv = [login_shell, "-l"]
        raw_cwd = working_dir

    if tmux_manager.is_available() and check:
        session_name = tmux_manager.session_name_for_check(check, where=where)
        tmux_manager.ensure_session(
            session_name, cwd=raw_cwd, inner_argv=raw_argv, init_command=raw_init
        )
        argv = ["tmux", "-u", "attach-session", "-t", session_name]
        label = "tmux [%s] · %s" % (session_name, raw_label)
        return argv, raw_cwd, label, ""

    return raw_argv, raw_cwd, raw_label, raw_init


def child_environment():
    """Environment for the shell: never hand it the cockpit's own password."""
    env = dict(os.environ)
    for leaked in ("STATUS_PASSWORD", "STATUS_USER"):
        env.pop(leaked, None)
    env["TERM"] = "xterm-256color"
    env.setdefault("COLORTERM", "truecolor")
    return env


def set_winsize(fd, rows, cols):
    rows = max(1, min(int(rows), 500))
    cols = max(1, min(int(cols), 500))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


# --------------------------------------------------------------------------- #
# Session
# --------------------------------------------------------------------------- #
def run_session(sock, argv, cwd, idle_timeout=900, init=""):
    """Pump bytes between a WebSocket and a PTY until either side closes."""
    master_fd, slave_fd = pty.openpty()
    set_winsize(master_fd, 24, 80)

    try:
        process = subprocess.Popen(
            argv,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env=child_environment(),
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        os.close(master_fd)
        os.close(slave_fd)
        message = "failed to start shell: %s\r\n" % exc
        try:
            sock.sendall(encode_frame(message.encode(), OP_BINARY))
            sock.sendall(encode_frame(b"", OP_CLOSE))
        except OSError:
            pass
        return

    os.close(slave_fd)

    if init:
        # Give the login shell a moment to finish sourcing its rc files,
        # otherwise the typed line can land before the prompt is ready.
        time.sleep(0.4)
        try:
            os.write(master_fd, init.encode())
        except OSError:
            pass

    reader = FrameReader()
    last_activity = time.monotonic()
    sock.setblocking(False)

    try:
        while True:
            if process.poll() is not None:
                _drain_pty(sock, master_fd)
                break
            if time.monotonic() - last_activity > idle_timeout:
                _send(sock, b"\r\n[session idle - closed by server]\r\n")
                break

            try:
                readable, _, _ = select.select([sock, master_fd], [], [], 1.0)
            except (OSError, ValueError):
                break

            if master_fd in readable:
                try:
                    data = os.read(master_fd, READ_SIZE)
                except OSError:
                    data = b""
                if not data:
                    break
                if not _send(sock, data):
                    break
                last_activity = time.monotonic()

            if sock in readable:
                try:
                    chunk = sock.recv(READ_SIZE)
                except OSError as exc:
                    if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                        continue
                    break
                if not chunk:
                    break
                last_activity = time.monotonic()
                reader.feed(chunk)
                if not _handle_frames(reader, sock, master_fd):
                    break
    finally:
        _shutdown(sock, process, master_fd)


def _handle_frames(reader, sock, master_fd):
    """Apply buffered client frames. Returns False when the client closed."""
    for opcode, payload in reader.frames():
        if opcode == OP_CLOSE:
            return False
        if opcode == OP_PING:
            _raw_send(sock, encode_frame(payload, OP_PONG))
        elif opcode == OP_BINARY:
            try:
                os.write(master_fd, payload)
            except OSError:
                return False
        elif opcode == OP_TEXT:
            # Control channel: {"resize": [cols, rows]}
            try:
                message = json.loads(payload.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if "resize" in message:
                cols, rows = message["resize"]
                try:
                    set_winsize(master_fd, rows, cols)
                except OSError:
                    pass
    return True


def _drain_pty(sock, master_fd):
    """Flush whatever the shell printed just before exiting."""
    while True:
        try:
            readable, _, _ = select.select([master_fd], [], [], 0.1)
            if master_fd not in readable:
                return
            data = os.read(master_fd, READ_SIZE)
        except OSError:
            return
        if not data or not _send(sock, data):
            return


def _send(sock, data):
    return _raw_send(sock, encode_frame(data, OP_BINARY))


def _raw_send(sock, frame):
    total = 0
    while total < len(frame):
        try:
            readable = select.select([], [sock], [], 5.0)[1]
            if not readable:
                return False
            total += sock.send(frame[total:])
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                continue
            return False
    return True


def _shutdown(sock, process, master_fd):
    try:
        _raw_send(sock, encode_frame(b"", OP_CLOSE))
    except OSError:
        pass
    if process.poll() is None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGHUP)
        except OSError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except OSError:
                pass
    try:
        os.close(master_fd)
    except OSError:
        pass
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
