#!/usr/bin/env python3
"""
UCI TCP Server — Makes the chess engine available over TCP for remote XBoard.

Runs on RHEL host (10.10.0.100), listens on port 5000.
XBoard on laptop connects via:
    xboard -fcp "tcp/10.10.0.100/5000 --proto xc"
"""

import argparse
import os
import socket
import subprocess
import sys
import threading

UCI_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chess_uci.py")
DEFAULT_PORT = 5000
DEFAULT_HOST = "0.0.0.0"


def _read_engine(engine_proc, client_sock):
    """Forward engine stdout to TCP client."""
    try:
        while True:
            line = engine_proc.stdout.readline()
            if not line:
                break
            client_sock.sendall(line.encode())
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        try:
            engine_proc.terminate()
        except Exception:
            pass


def _read_client(engine_proc, client_sock):
    """Forward TCP client stdin to engine."""
    try:
        client_sock.settimeout(1)
        buf = b""
        while True:
            try:
                chunk = client_sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    cmd = line.decode("utf-8") + "\n"
                    engine_proc.stdin.write(cmd)
                    engine_proc.stdin.flush()
                    if cmd.strip().lower().startswith("quit"):
                        return
            except socket.timeout:
                continue
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass


def relay(engine_proc, client_sock):
    """Bidirectional relay between engine and TCP client."""
    t1 = threading.Thread(target=_read_engine, args=(engine_proc, client_sock), daemon=True)
    t2 = threading.Thread(target=_read_client, args=(engine_proc, client_sock), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    try:
        client_sock.close()
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="UCI TCP Server for XBoard")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port (default 5000)")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="Bind address (default 0.0.0.0)")
    parser.add_argument("--depth", type=int, default=3, help="Search depth (default 3)")
    args = parser.parse_args()

    if not os.path.exists(UCI_SCRIPT):
        print(f"ERROR: UCI script not found at {UCI_SCRIPT}", file=sys.stderr)
        sys.exit(1)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(1)
    print(f"UCI TCP server listening on {args.host}:{args.port}")
    print(f"On your laptop, run:")
    print(f"  xboard -fcp \"tcp/10.10.0.100/{args.port} --proto xc\"")

    try:
        while True:
            client_sock, addr = server.accept()
            print(f"Connected from {addr[0]}:{addr[1]}", flush=True)
            engine_proc = subprocess.Popen(
                [sys.executable, UCI_SCRIPT, "--depth", str(args.depth)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            relay(engine_proc, client_sock)
            print(f"Disconnected {addr[0]}", flush=True)
    except KeyboardInterrupt:
        print("\nStopping...", flush=True)
    finally:
        server.close()


if __name__ == "__main__":
    main()
