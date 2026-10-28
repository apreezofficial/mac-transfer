"""Run this on Windows. Sends the folders below to receive.py on the Mac.

    python send.py                    # asks for the Mac's address and pairing code
    python send.py --dry-run          # just show what would be sent and how big it is
    python send.py --only htdocs      # send one folder
    python send.py --everything       # don't skip node_modules / vendor / build output
"""
import argparse
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Name on the Mac -> folder on this PC
SOURCES = {
    "ap": r"C:\Users\HP\Desktop\ap",
    "gigs": r"C:\Users\HP\Desktop\gigs",
    "my job(geeks)": r"C:\Users\HP\Desktop\my job(geeks)",
    "htdocs": r"C:\xampp\htdocs",
}

# Folders that get rebuilt with npm install / composer install / a fresh build,
# and that hold Windows-only binaries that wouldn't run on the Mac anyway.
SKIP_DIRS = {"node_modules", ".next", ".expo", ".gradle", ".turbo", ".parcel-cache",
             "__pycache__", ".venv", "venv"}
SKIP_FILES = {"Thumbs.db", "desktop.ini"}

XAMPP_MYSQL_BIN = Path(r"C:\xampp\mysql\bin")
SYSTEM_DBS = {"information_schema", "performance_schema", "mysql", "sys", "phpmyadmin", "test"}
CHUNK = 1 << 20


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Mac disconnected")
        buf += chunk
    return bytes(buf)


def recv_msg(sock):
    (n,) = struct.unpack("!I", recv_exact(sock, 4))
    return json.loads(recv_exact(sock, n))


def send_msg(sock, obj):
    data = json.dumps(obj).encode()
    sock.sendall(struct.pack("!I", len(data)) + data)


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def long_path(p):
    # Lets Windows open paths longer than 260 characters.
    p = os.path.abspath(p)
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def is_link(path):
    return os.path.islink(path) or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


def should_skip_dir(parent, name, everything):
    if everything:
        return False
    if name in SKIP_DIRS:
        return True
    # PHP dependencies: only skip vendor/ when composer.json can bring it back.
    if name == "vendor" and os.path.exists(os.path.join(parent, "composer.json")):
        return True
    # Android build output inside React Native / Flutter projects.
    if name in ("build", ".cxx") and "android" in Path(parent).parts:
        return True
    return False


def scan(sources, everything):
    """Returns (dirs, files, skipped) where files are [mac_path, size, mtime, local_path]."""
    dirs, files, skipped = [], [], []
    for name, root in sources.items():
        if not os.path.isdir(root):
            print(f"  ! {root} not found, skipping")
            continue
        root = long_path(root)
        for here, subdirs, filenames in os.walk(root):
            rel_here = os.path.relpath(here, root)
            mac_here = name if rel_here == "." else f"{name}/{rel_here.replace(os.sep, '/')}"
            keep = []
            for d in subdirs:
                full = os.path.join(here, d)
                if is_link(full):
                    continue
                if should_skip_dir(here, d, everything):
                    skipped.append(f"{mac_here}/{d}")
                else:
                    keep.append(d)
            subdirs[:] = keep
            dirs.append(mac_here)
            for f in filenames:
                full = os.path.join(here, f)
                if f in SKIP_FILES or is_link(full):
                    continue
                try:
                    st = os.stat(full)
                except OSError as e:
                    print(f"  ! can't read {full}: {e}")
                    continue
                files.append([f"{mac_here}/{f}", st.st_size, st.st_mtime, full])
    return dirs, files, skipped


def export_databases(out_dir):
    """Dumps the XAMPP MySQL databases to one .sql file. Returns its path, or None."""
    mysql, mysqldump = XAMPP_MYSQL_BIN / "mysql.exe", XAMPP_MYSQL_BIN / "mysqldump.exe"
    if not mysqldump.exists():
        print("  ! mysqldump not found, skipping databases")
        return None
    try:
        names = subprocess.run([str(mysql), "-u", "root", "-N", "-e", "SHOW DATABASES"],
                               capture_output=True, text=True, check=True).stdout.split()
    except subprocess.CalledProcessError as e:
        print(f"  ! couldn't reach MySQL ({e.stderr.strip()})")
        print("    Start MySQL in the XAMPP Control Panel and run again to include databases.")
        return None
    names = [n for n in names if n.lower() not in SYSTEM_DBS]
    if not names:
        print("  No databases of your own found.")
        return None
    out = Path(out_dir) / "xampp-databases.sql"
    with open(out, "wb") as fh:
        subprocess.run([str(mysqldump), "-u", "root", "--routines", "--events", "--triggers",
                        "--single-transaction", "--databases", *names], stdout=fh, check=True)
    print(f"  Exported {len(names)} databases: {', '.join(names)} ({human(out.stat().st_size)})")
    return out


def send_file(sock, i, path, progress):
    try:
        fh = open(path, "rb")
    except OSError as e:
        send_msg(sock, {"i": i, "error": str(e)})
        return False
    with fh:
        size = os.fstat(fh.fileno()).st_size
        send_msg(sock, {"i": i, "size": size})
        h, left = hashlib.sha256(), size
        while left:
            try:
                chunk = fh.read(min(CHUNK, left))
            except OSError:
                chunk = b""
            if not chunk:
                # File shrank or became unreadable mid-send. Pad so the stream stays in step;
                # the padding isn't hashed, so the Mac sees a checksum mismatch and discards it.
                sock.sendall(b"\0" * left)
                progress(left)
                break
            sock.sendall(chunk)
            h.update(chunk)
            left -= len(chunk)
            progress(len(chunk))
        sock.sendall(h.digest())
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", help="Mac address shown by receive.py")
    ap.add_argument("--code", help="pairing code shown by receive.py")
    ap.add_argument("--port", type=int, default=50505)
    ap.add_argument("--only", action="append", choices=list(SOURCES), help="send just this folder")
    ap.add_argument("--everything", action="store_true", help="include node_modules, vendor, etc.")
    ap.add_argument("--no-db", action="store_true", help="don't export the XAMPP databases")
    ap.add_argument("--dry-run", action="store_true", help="show sizes without sending")
    args = ap.parse_args()

    sources = {k: v for k, v in SOURCES.items() if not args.only or k in args.only}

    print("Scanning folders...")
    dirs, files, skipped = scan(sources, args.everything)
    by_top = {}
    for mac_path, size, *_ in files:
        top = mac_path.split("/", 1)[0]
        by_top[top] = by_top.get(top, 0) + size
    for top, size in by_top.items():
        print(f"  {top:<16} {sum(1 for f in files if f[0].startswith(top + '/')):>7} files  {human(size)}")
    print(f"  Skipped {len(skipped)} dependency/build folders (reinstall them on the Mac)")
    print(f"  Total: {len(files)} files, {human(sum(f[1] for f in files))}")

    if args.dry_run:
        Path("skipped-folders.txt").write_text("\n".join(skipped) + "\n", encoding="utf-8")
        print("Dry run: skipped folders listed in skipped-folders.txt")
        return

    tmp = tempfile.mkdtemp(prefix="mac-transfer-")
    try:
        if not args.no_db:
            print("Exporting XAMPP databases...")
            dump = export_databases(tmp)
            if dump:
                st = dump.stat()
                files.append(["databases/xampp-databases.sql", st.st_size, st.st_mtime, str(dump)])
                dirs.append("databases")

        ip = args.ip or input("\nMac address (from receive.py): ").strip()
        code = args.code or input("Pairing code: ").strip()

        sock = socket.create_connection((ip, args.port), timeout=15)
        sock.settimeout(120)
        with sock:
            send_msg(sock, {"code": code, "dirs": dirs, "files": [f[:3] for f in files]})
            reply = recv_msg(sock)
            if not reply["ok"]:
                sys.exit(f"Mac refused: {reply['reason']}")
            need = reply["need"]
            total = sum(files[i][1] for i in need)
            print(f"\n{len(files) - len(need)} files already on the Mac. "
                  f"Sending {len(need)} files ({human(total)})...")

            sent, start = 0, time.time()

            def progress(n):
                nonlocal sent
                sent += n
                elapsed = max(time.time() - start, 0.001)
                rate = sent / elapsed
                eta = (total - sent) / rate if rate else 0
                print(f"\r  {human(sent)} / {human(total)}  {human(rate)}/s  "
                      f"~{int(eta // 60)}m{int(eta % 60):02d}s left   ", end="", flush=True)

            unreadable = []
            for i in need:
                if not send_file(sock, i, files[i][3], progress):
                    unreadable.append(files[i][0])
            send_msg(sock, {"done": True})
            summary = recv_msg(sock)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n\nDone: {summary['ok']} files copied and checksum-verified, "
          f"{len(summary['failed'])} failed.")
    if summary["failed"]:
        Path("failed-files.txt").write_text(
            "\n".join(f"{rel}\t{why}" for rel, why in summary["failed"]) + "\n", encoding="utf-8")
        print("Failed files are in failed-files.txt. Close any app using them and run again;")
        print("files already copied are skipped.")


if __name__ == "__main__":
    try:
        main()
    except (ConnectionError, OSError) as e:
        sys.exit(f"\nConnection problem: {e}\nRun send.py again; it picks up where it stopped.")
    except KeyboardInterrupt:
        sys.exit("\nStopped. Run send.py again to resume.")
