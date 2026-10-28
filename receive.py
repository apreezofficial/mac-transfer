#!/usr/bin/env python3
"""Run this on the Mac. Waits for send.py (on Windows) and saves the folders.

    python3 receive.py                 # saves to ~/Desktop/from-windows
    python3 receive.py --dest ~/Projects
"""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import socket
import struct
import time
from pathlib import Path

CHUNK = 1 << 20


def recv_exact(conn, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = conn.recv(min(n - len(buf), CHUNK))
        if not chunk:
            raise ConnectionError("sender disconnected")
        buf += chunk
    return bytes(buf)


def recv_msg(conn):
    (n,) = struct.unpack("!I", recv_exact(conn, 4))
    return json.loads(recv_exact(conn, n))


def send_msg(conn, obj):
    data = json.dumps(obj).encode()
    conn.sendall(struct.pack("!I", len(data)) + data)


def local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def safe_target(dest, rel):
    """Map a sender path like 'gigs/app/index.js' into dest, refusing anything that escapes it."""
    parts = rel.split("/")
    if not rel or rel.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"unsafe path: {rel!r}")
    return dest.joinpath(*parts)


def is_complete(path, size, mtime):
    try:
        st = path.stat()
    except OSError:
        return False
    return st.st_size == size and int(st.st_mtime) == int(mtime)


def handle(conn, dest, code):
    hello = recv_msg(conn)
    if hello.get("code") != code:
        send_msg(conn, {"ok": False, "reason": "wrong pairing code"})
        print("  Rejected: wrong pairing code.")
        return

    for rel in hello["dirs"]:
        safe_target(dest, rel).mkdir(parents=True, exist_ok=True)

    manifest = hello["files"]
    need = [i for i, (rel, size, mtime) in enumerate(manifest)
            if not is_complete(safe_target(dest, rel), size, mtime)]
    total = sum(manifest[i][1] for i in need)

    free = shutil.disk_usage(dest).free
    if total > free:
        send_msg(conn, {"ok": False, "reason": f"Mac needs {human(total)} free, has {human(free)}"})
        print(f"  Not enough disk space: need {human(total)}, have {human(free)}.")
        return

    send_msg(conn, {"ok": True, "need": need})
    print(f"  {len(manifest) - len(need)} files already here, receiving {len(need)} ({human(total)})")

    need_set = set(need)
    ok, failed, done_bytes, start = 0, [], 0, time.time()
    for _ in need:
        hdr = recv_msg(conn)
        i = hdr["i"]
        if i not in need_set:
            raise ValueError(f"unexpected file index {i}")
        rel, _size, mtime = manifest[i]
        if "error" in hdr:
            failed.append([rel, hdr["error"]])
            continue

        target = safe_target(dest, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        h, left = hashlib.sha256(), hdr["size"]
        with open(part, "wb") as out:
            while left:
                chunk = conn.recv(min(CHUNK, left))
                if not chunk:
                    raise ConnectionError("sender disconnected")
                out.write(chunk)
                h.update(chunk)
                left -= len(chunk)
                done_bytes += len(chunk)
        digest = recv_exact(conn, 32)

        if digest == h.digest():
            os.replace(part, target)
            os.utime(target, (mtime, mtime))
            ok += 1
        else:
            part.unlink(missing_ok=True)
            failed.append([rel, "checksum mismatch (file changed while sending?)"])

        elapsed = max(time.time() - start, 0.001)
        print(f"\r  {human(done_bytes)} / {human(total)}  {human(done_bytes / elapsed)}/s   ",
              end="", flush=True)

    recv_msg(conn)  # {"done": true}
    send_msg(conn, {"ok": ok, "failed": failed})
    print(f"\n  Finished: {ok} received, {len(failed)} failed.")
    if failed:
        report = dest / "transfer-failures.txt"
        report.write_text("\n".join(f"{rel}\t{why}" for rel, why in failed) + "\n")
        print(f"  Failures listed in {report}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=str(Path.home() / "Desktop" / "from-windows"))
    ap.add_argument("--port", type=int, default=50505)
    args = ap.parse_args()

    dest = Path(args.dest).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    code = f"{secrets.randbelow(10**6):06d}"

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", args.port))
    server.listen(1)

    print(f"Saving to:     {dest}")
    print(f"Mac address:   {local_ip()}")
    print(f"Pairing code:  {code}")
    print("Waiting for Windows... (Ctrl+C to quit)\n")

    while True:
        conn, addr = server.accept()
        print(f"Connected: {addr[0]}")
        try:
            with conn:
                handle(conn, dest, code)
        except (ConnectionError, ValueError, OSError) as e:
            print(f"\n  Transfer interrupted: {e}. Run send.py again to resume.")
        print("\nWaiting for Windows... (Ctrl+C to quit)\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye.")
