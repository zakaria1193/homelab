#!/usr/bin/env python3
"""aicli's HTTP service: a localhost-only OpenAI-compatible chat-completions
front end for text callers like ai-job-search. Each request runs the real
`claude`/`agy` CLI once, through the same argv builder as `aicli run`. It
never reads OAuth tokens and never opens a network connection other than its
own listening socket - every vendor call goes through the CLI subprocess
under the user's own login. See ticket homelab-0013 for the why.
"""
import ipaddress
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import aicli  # noqa: E402

# Flags the service adds that a caller exec-ing the CLI itself never needs,
# so they live here rather than in aicli.toml (see homelab-0013 criterion 1).
PRINT_FLAG = {"claude": "-p", "agy": "--print"}
STREAM_ARGS = {
    "claude": ["--output-format", "stream-json", "--verbose"],
    "agy": ["--output-format", "stream-json"],
}
STREAM_FORMAT = {"claude": "claude", "agy": "agy"}
# Without streaming, claude still prints JSON so its token counts can be read.
# agy's plain `--output-format json` shape isn't confirmed, so agy stays text.
ONCE_ARGS = {"claude": ["--output-format", "json"], "agy": []}

DEFAULT_USAGE_LOG = Path("~/.local/state/aicli/usage.jsonl").expanduser()
_usage_lock = threading.Lock()

MAX_ARG_PROMPT_BYTES = 120 * 1024  # Linux caps one argv argument at 128 KiB


class ApiError(Exception):
    def __init__(self, status, message, code="invalid_request_error"):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


def error_body(message, code="invalid_request_error"):
    return {"error": {"message": message, "type": code}}


def model_ids():
    ids = list(aicli.TOOLS)
    for tool in aicli.TOOLS:
        for tier in aicli.TIERS:
            ids.append(f"{tool}/{tier}")
    return ids


def parse_model_id(model_id):
    if "/" in model_id:
        tool, tier = model_id.split("/", 1)
    else:
        tool, tier = model_id, "default"
    return tool, tier


def _content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return "" if content is None else str(content)


def flatten_messages(messages):
    """System text first, then the turns. A single user message passes
    through as it is - see homelab-0013's service spec."""
    if len(messages) == 1 and messages[0].get("role") == "user":
        return _content_text(messages[0].get("content"))
    parts = []
    system_text = "\n".join(
        _content_text(m.get("content")) for m in messages if m.get("role") == "system"
    )
    if system_text:
        parts.append(system_text)
    for m in messages:
        if m.get("role") == "system":
            continue
        parts.append(f"{m.get('role')}: {_content_text(m.get('content'))}")
    return "\n\n".join(parts)


def build_run_argv(config, tool, tier, effort, prompt, stream):
    extra = (STREAM_ARGS if stream else ONCE_ARGS)[tool] + [PRINT_FLAG[tool], prompt]
    argv = aicli.build_argv(config, tool, tier, effort, extra)
    if argv is None:
        raise ApiError(502, f"{tool} CLI not found", code="upstream_error")
    return argv


# --- token usage -------------------------------------------------------------

_CLAUDE_MODEL_KEYS = {"inputTokens": "input", "outputTokens": "output",
                      "cacheCreationInputTokens": "cache_write", "cacheReadInputTokens": "cache_read"}
_USAGE_KEYS = {"input_tokens": "input", "prompt_tokens": "input",
               "output_tokens": "output", "completion_tokens": "output",
               "cache_creation_input_tokens": "cache_write", "cache_read_input_tokens": "cache_read",
               "total_tokens": "total"}


def _counts(raw, keys):
    out = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
    for key, kind in keys.items():
        value = raw.get(key)
        if isinstance(value, (int, float)):
            out[kind] = out.get(kind, 0) + int(value)
    if not out.get("total"):
        out["total"] = out["input"] + out["output"] + out["cache_write"] + out["cache_read"]
    return out


def usage_of(tool, result, model):
    """Token counts per model from the CLI's final result: {model: counts}, or
    None when the CLI reported none. claude gives `modelUsage` per model (and
    a flat `usage`); agy gives a flat `usage` under its result."""
    if not isinstance(result, dict):
        return None
    if tool == "claude" and isinstance(result.get("modelUsage"), dict) and result["modelUsage"]:
        return {m: _counts(u, _CLAUDE_MODEL_KEYS)
                for m, u in result["modelUsage"].items() if isinstance(u, dict)}
    usage = result.get("usage")
    if tool == "agy" and not isinstance(usage, dict) and isinstance(result.get("result"), dict):
        usage = result["result"].get("usage")
    if isinstance(usage, dict) and usage:
        return {model or tool: _counts(usage, _USAGE_KEYS)}
    return None


def usage_rows(tool, tier, stream, usage, model, now=None):
    """One log line per model. A run that reported nothing still gets a line,
    so the request is counted."""
    at = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    base = {"at": at, "tool": tool, "tier": tier, "stream": stream}
    if not usage:
        return [{**base, "model": model or tool, "reported": False}]
    return [{**base, "model": m, "reported": True, **counts} for m, counts in usage.items()]


def record_usage(path, rows):
    """Append to the JSONL usage log. A log that can't be written never fails
    the request."""
    if not path:
        return
    try:
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _usage_lock, open(path, "a") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
    except OSError as e:
        print(f"aicli-ai: usage log not written: {e}", file=sys.stderr)


def tier_model(config, tool, tier):
    return (config.get(tool) or {}).get("tiers", {}).get(tier)


def run_once(config, tool, tier, effort, prompt, timeout, usage_out=None):
    """One non-streaming CLI run in an empty scratch directory. Returns the
    answer text; claude's token counts go into `usage_out["result"]`."""
    argv = build_run_argv(config, tool, tier, effort, prompt, stream=False)
    with tempfile.TemporaryDirectory(prefix="aicli-") as scratch:
        try:
            proc = subprocess.run(
                argv, cwd=scratch, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise ApiError(504, f"{tool} call timed out after {timeout}s", code="timeout")
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-2000:]
        raise ApiError(502, f"{tool} exited {proc.returncode}: {tail}", code="upstream_error")
    if not ONCE_ARGS[tool]:
        return proc.stdout
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return proc.stdout
    if not isinstance(data, dict) or not isinstance(data.get("result"), str):
        return proc.stdout
    if usage_out is not None:
        usage_out["result"] = data
    return data["result"]


def run_stream(config, tool, tier, effort, prompt, timeout, usage_out=None):
    """Yields text deltas from the CLI's stream-json output as they arrive.

    The final result event (with the token counts) goes into
    `usage_out["result"]`. Raises ApiError(504) on a timeout or ApiError(502) on a non-zero exit -
    but only once the generator is driven past its last delta; see
    _stream_response for how the caller turns that into an HTTP status only
    when no bytes have gone out yet. Closing the generator early (a client
    disconnect) kills the CLI process via the `finally` below.
    """
    argv = build_run_argv(config, tool, tier, effort, prompt, stream=True)
    fmt = STREAM_FORMAT[tool]
    emitted = False

    def _deltas(line):
        nonlocal emitted
        line = line.strip()
        if not line or not line.startswith("{"):
            return
        try:
            evt = json.loads(line)
        except ValueError:
            return
        if fmt == "claude":
            if evt.get("type") == "assistant":
                for block in (evt.get("message") or {}).get("content") or []:
                    if block.get("type") == "text" and block.get("text"):
                        emitted = True
                        yield block["text"]
            elif evt.get("type") == "result":
                if usage_out is not None:
                    usage_out["result"] = evt
                if not emitted and evt.get("result"):
                    yield evt["result"]
        elif fmt == "agy":
            if evt.get("event") == "step_update":
                delta = (evt.get("step_update") or {}).get("text_delta")
                if delta:
                    emitted = True
                    yield delta
            elif evt.get("event") == "result":
                if usage_out is not None:
                    usage_out["result"] = evt
                text = (evt.get("result") or {}).get("response") if not emitted else None
                if text:
                    yield text

    with tempfile.TemporaryDirectory(prefix="aicli-") as scratch:
        proc = subprocess.Popen(
            argv, cwd=scratch, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        stderr_chunks = []

        def _drain_stderr():
            for line in proc.stderr:
                stderr_chunks.append(line)

        drain = threading.Thread(target=_drain_stderr, daemon=True)
        drain.start()

        timed_out = threading.Event()

        def _on_timeout():
            timed_out.set()
            try:
                proc.kill()
            except OSError:
                pass

        timer = threading.Timer(timeout, _on_timeout)
        timer.start()
        try:
            while True:
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                for delta in _deltas(line):
                    yield delta
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            drain.join(timeout=1)
            proc.stdout.close()
            proc.stderr.close()

    if timed_out.is_set():
        raise ApiError(504, f"{tool} call timed out after {timeout}s", code="timeout")
    if proc.returncode != 0:
        tail = "".join(stderr_chunks)[-2000:]
        raise ApiError(502, f"{tool} exited {proc.returncode}: {tail}", code="upstream_error")


def chat_completion_object(model_id, text):
    now = int(time.time())
    return {
        "id": f"chatcmpl-aicli-{now}",
        "object": "chat.completion",
        "created": now,
        "model": model_id,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def chat_completion_chunk(model_id, content=None, finish_reason=None):
    delta = {}
    if content is not None:
        delta["content"] = content
    return {
        "id": "chatcmpl-aicli",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "aicli-ai/1.0"

    def log_message(self, format, *args):
        pass  # the unit's journal/systemd log is enough; keep tests quiet

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status, message, code="invalid_request_error"):
        self._send_json(status, error_body(message, code))

    def do_GET(self):
        if self.path == "/healthz":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/v1/models":
            self._send_json(200, {
                "object": "list",
                "data": [{"id": i, "object": "model"} for i in model_ids()],
            })
            return
        self._send_error(404, "not found")

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self._send_error(404, "not found")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError:
            self._send_error(400, "invalid JSON body")
            return
        try:
            self._handle_chat_completions(payload)
        except ApiError as e:
            self._send_error(e.status, e.message, e.code)

    def _handle_chat_completions(self, payload):
        config = self.server.aicli_config
        if not isinstance(payload, dict):
            raise ApiError(400, "invalid JSON body")
        if payload.get("tools"):
            raise ApiError(400, "tools are not supported")

        model_id = payload.get("model")
        if not model_id:
            raise ApiError(400, "model is required")
        tool, tier = parse_model_id(model_id)
        if tool not in aicli.TOOLS or tier not in aicli.TIERS:
            raise ApiError(
                400,
                f"unknown model {model_id!r}: valid ids are {', '.join(model_ids())}",
            )

        messages = payload.get("messages")
        if not messages:
            raise ApiError(400, "messages must not be empty")
        prompt = flatten_messages(messages)

        effort = payload.get("reasoning_effort")
        if effort is not None and effort not in aicli.EFFORTS:
            raise ApiError(400, f"invalid reasoning_effort {effort!r}")

        if len(prompt.encode("utf-8")) > MAX_ARG_PROMPT_BYTES:
            raise ApiError(413, "prompt too large for a single CLI argument")

        timeout = self.server.aicli_timeout
        stream = bool(payload.get("stream"))
        got = {}
        try:
            if stream:
                self._stream_response(config, tool, tier, effort, prompt, timeout, model_id, got)
            else:
                with self.server.aicli_semaphore:
                    text = run_once(config, tool, tier, effort, prompt, timeout, got)
                self._send_json(200, chat_completion_object(model_id, text))
        finally:
            # every run is logged, a failed one too: it is a request all the same
            model = tier_model(config, tool, tier)
            record_usage(self.server.aicli_usage_log, usage_rows(
                tool, tier, stream, usage_of(tool, got.get("result"), model), model))

    def _stream_response(self, config, tool, tier, effort, prompt, timeout, model_id, got):
        with self.server.aicli_semaphore:
            gen = run_stream(config, tool, tier, effort, prompt, timeout, got)
            sentinel = object()
            first = next(gen, sentinel)  # may raise ApiError before any bytes go out

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                if first is not sentinel:
                    self._write_chunk(model_id, first)
                for delta in gen:
                    self._write_chunk(model_id, delta)
            except (BrokenPipeError, ConnectionResetError, ApiError):
                gen.close()
                return
            gen.close()
            self._write_chunk(model_id, None, finish_reason="stop")
            self.wfile.write(b"data: [DONE]\n\n")

    def _write_chunk(self, model_id, content, finish_reason=None):
        chunk = chat_completion_chunk(model_id, content, finish_reason)
        self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
        self.wfile.flush()


def _is_loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    if host == "localhost":
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return all(ipaddress.ip_address(info[4][0]).is_loopback for info in infos)


def make_server(config, host, port, max_concurrent, timeout, usage_log=None):
    if not _is_loopback(host):
        print(f"aicli-ai: refusing to bind non-loopback host {host!r}", file=sys.stderr)
        raise SystemExit(2)
    server = ThreadingHTTPServer((host, port), Handler)
    server.aicli_config = config
    server.aicli_semaphore = threading.Semaphore(max_concurrent)
    server.aicli_timeout = timeout
    server.aicli_usage_log = usage_log
    return server


def main():
    config = aicli.load_config()
    host = os.environ.get("AICLI_HOST", "127.0.0.1")
    port = int(os.environ.get("AICLI_PORT", "8500"))
    max_concurrent = int(os.environ.get("AICLI_MAX_CONCURRENT", "2"))
    timeout = int(os.environ.get("AICLI_TIMEOUT", "600"))
    usage_log = os.environ.get("AICLI_USAGE_LOG") or str(DEFAULT_USAGE_LOG)
    server = make_server(config, host, port, max_concurrent, timeout, usage_log)
    print(f"aicli-ai listening on http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
