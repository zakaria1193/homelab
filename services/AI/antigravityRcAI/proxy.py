#!/usr/bin/env python3
import asyncio
import os
import sys

LISTEN_HOST = os.environ.get("AGY_PROXY_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("AGY_PROXY_PORT", "4400"))
TARGET_HOST = "127.0.0.1"
TARGET_PORT = int(os.environ.get("AGY_TARGET_PORT", "4401"))

async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()

async def handle_client(client_reader, client_writer):
    try:
        target_reader, target_writer = await asyncio.open_connection(TARGET_HOST, TARGET_PORT)
    except Exception as e:
        client_writer.close()
        return

    # Rewrite Host header to localhost so agy's host-header check passes
    header_buf = bytearray()
    while b"\r\n\r\n" not in header_buf:
        chunk = await client_reader.read(4096)
        if not chunk:
            break
        header_buf.extend(chunk)
        if len(header_buf) > 65536:
            break

    if b"\r\n\r\n" in header_buf:
        parts = header_buf.split(b"\r\n\r\n", 1)
        headers_raw = parts[0].decode("latin1", errors="ignore")
        body = parts[1]

        lines = headers_raw.split("\r\n")
        new_lines = []
        for line in lines:
            if line.lower().startswith("host:"):
                new_lines.append("Host: 127.0.0.1:4400")
            else:
                new_lines.append(line)
        new_headers = "\r\n".join(new_lines).encode("latin1") + b"\r\n\r\n" + body
        target_writer.write(new_headers)
        await target_writer.drain()
    else:
        target_writer.write(header_buf)
        await target_writer.drain()

    asyncio.create_task(pipe(client_reader, target_writer))
    asyncio.create_task(pipe(target_reader, client_writer))

async def main():
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    print(f"Proxy listening on {LISTEN_HOST}:{LISTEN_PORT} -> {TARGET_HOST}:{TARGET_PORT}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
