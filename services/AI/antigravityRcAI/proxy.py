#!/usr/bin/env python3
import asyncio
import os
import sys

LISTEN_HOST = os.environ.get("AGY_PROXY_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("AGY_PROXY_PORT", "4400"))
TARGET_HOST = "127.0.0.1"
TARGET_PORT = int(os.environ.get("AGY_TARGET_PORT", "4401"))

def rewrite_headers(data):
    if b"\r\n\r\n" not in data:
        return data
    parts = data.split(b"\r\n\r\n", 1)
    headers_raw = parts[0].decode("latin1", errors="ignore")
    body = parts[1]
    
    # Only rewrite HTTP request headers (GET, POST, OPTIONS, PUT, DELETE, Upgrade)
    first_line = headers_raw.split("\r\n")[0] if headers_raw else ""
    if not any(first_line.startswith(m) for m in ("GET ", "POST ", "PUT ", "DELETE ", "OPTIONS ", "HEAD ", "PATCH ")):
        return data

    lines = headers_raw.split("\r\n")
    new_lines = []
    has_host = False
    for line in lines:
        if line.lower().startswith("host:"):
            new_lines.append(f"Host: 127.0.0.1:{TARGET_PORT}")
            has_host = True
        else:
            new_lines.append(line)
    if not has_host:
        new_lines.append(f"Host: 127.0.0.1:{TARGET_PORT}")
        
    return "\r\n".join(new_lines).encode("latin1") + b"\r\n\r\n" + body

async def forward_stream(reader, writer, is_request=False):
    buf = bytearray()
    headers_processed = False
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break

            if is_request and not headers_processed:
                buf.extend(chunk)
                if b"\r\n\r\n" in buf:
                    rewritten = rewrite_headers(bytes(buf))
                    writer.write(rewritten)
                    await writer.drain()
                    headers_processed = True
                    buf.clear()
            else:
                writer.write(chunk)
                await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass

async def handle_client(client_reader, client_writer):
    try:
        target_reader, target_writer = await asyncio.open_connection(TARGET_HOST, TARGET_PORT)
    except Exception:
        client_writer.close()
        return

    asyncio.create_task(forward_stream(client_reader, target_writer, is_request=True))
    asyncio.create_task(forward_stream(target_reader, client_writer, is_request=False))

async def main():
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    print(f"Proxy listening on {LISTEN_HOST}:{LISTEN_PORT} -> {TARGET_HOST}:{TARGET_PORT}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
