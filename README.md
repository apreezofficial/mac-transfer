# Windows → Mac folder transfer

Copies `ap`, `gigs`, `my job(geeks)`, `C:\xampp\htdocs` and your XAMPP databases
from Windows to the Mac over Wi-Fi.

**Size:** about 52,600 files, 11.1 GB. Roughly 15–40 minutes on normal Wi-Fi, plus a few
minutes for the sender to scan the folders first.

## Before you start

- Mac and Windows PC on the **same Wi-Fi**.
- Plug both into power and keep the Mac awake (lid open).
- In the **XAMPP Control Panel**, click **Start** next to **MySQL** so the databases get exported.
- Close VS Code, Android Studio and other editors on Windows so no files are locked.

## 1. On the Mac

Open **Terminal** and run:

```bash
cd ~/Desktop
curl -O https://raw.githubusercontent.com/apreezofficial/mac-transfer/main/receive.py
python3 receive.py
```

- If macOS offers to install "command line developer tools", click **Install**, wait, then run
  `python3 receive.py` again.
- If it asks whether to allow incoming connections, click **Allow**.

It prints something like:

```
Mac address:   192.168.1.23
Pairing code:  357499
Waiting for Windows...
```

Leave this window open.

## 2. On Windows

Open a **new** terminal (PowerShell) and run:

```powershell
cd C:\Users\HP\Desktop\mac-transfer
python send.py
```

Type the **Mac address** and **pairing code** from step 1. If Windows asks whether Python can
use the network, allow it on **private networks**.

You'll see live progress:

```
  2.3 GB / 11.1 GB  12.4 MB/s  ~12m05s left
```

When it says `Done: ... files copied and checksum-verified`, the transfer is finished.

## If it stops partway

Run `python send.py` again with the same address and code. Files already on the Mac are skipped,
so it picks up where it stopped. If any files failed (usually because an app had them open),
they're listed in `failed-files.txt`. Close that app and run it again.

## What you get on the Mac

```
~/Desktop/from-windows/
  ap/  gigs/  my job(geeks)/  htdocs/
  databases/xampp-databases.sql
```

## After the transfer

Dependency folders were skipped, so reinstall them in each project:

```bash
npm install          # projects with package.json
composer install     # PHP projects with composer.json
```

Import the databases once MySQL is installed on the Mac (XAMPP for Mac, MAMP or
`brew install mysql`):

```bash
mysql -u root < ~/Desktop/from-windows/databases/xampp-databases.sql
```

## Options

| Command | What it does |
| --- | --- |
| `python send.py --dry-run` | Show what would be sent and the sizes, send nothing |
| `python send.py --only htdocs` | Send just one folder (`ap`, `gigs`, `my job(geeks)`, `htdocs`) |
| `python send.py --no-db` | Skip the database export |
| `python send.py --everything` | Also copy `node_modules`, `vendor` and build output |
| `python3 receive.py --dest ~/Projects` | Save somewhere other than `~/Desktop/from-windows` |

Skipped by default: `node_modules`, `vendor` (when `composer.json` exists), `.next`, `.expo`,
`.gradle`, `.turbo`, Python venvs and Android `build` folders.
