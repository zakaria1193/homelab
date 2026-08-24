#!/usr/bin/env python3
import asyncio
import os
import sys

LISTEN_HOST = os.environ.get("AGY_PROXY_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("AGY_PROXY_PORT", "4400"))
TARGET_HOST = "127.0.0.1"
TARGET_PORT = int(os.environ.get("AGY_TARGET_PORT", "4401"))

async def forward_stream(reader, writer, rewrite_host=False):
    first_chunk = True
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            if first_chunk and rewrite_host and b"\r\n\r\n" in data:
                parts = data.split(b"\r\n\r\n", 1)
                headers_raw = parts[0].decode("latin1", errors="ignore")
                body = parts[1]
                lines = headers_raw.split("\r\n")
                new_lines = []
                for line in lines:
                    if line.lower().startswith("host:"):
                        new_lines.append(f"Host: 127.0.0.1:{TARGET_PORT}")
                    else:
                        new_lines.append(line)
                data = "\r\n".join(new_lines).encode("latin1") + b"\r\n\r\n" + body
                first_chunk = False

            writer.write(data)
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
    except Exception as e:
        client_writer.close()
        return

    # Forward client -> target rewriting HTTP Host headers continuously for sub-requests / WebSockets
    asyncio.create_task(forward_stream(client_reader, target_writer, rewrite_host=True))
    # Forward target -> client transparently
    asyncio.create_task(forward_stream(target_reader, client_writer, rewrite_host=False))

async def main():
    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    print(f"Proxy listening on {LISTEN_HOST}:{LISTEN_PORT} -> {TARGET_HOST}:{TARGET_PORT}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
