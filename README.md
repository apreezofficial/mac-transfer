# Windows → Mac folder transfer

Copies `ap`, `gigs`, `my job(geeks)`, `C:\xampp\htdocs` and your XAMPP databases
over Wi-Fi. Both machines must be on the same network.

## 1. On the Mac

Copy `receive.py` to the Mac (AirDrop isn't available from Windows; email it to
yourself, use a USB stick or Google Drive). Then in Terminal:

```
cd ~/Downloads
python3 receive.py
```

If macOS offers to install "command line developer tools", accept and run it again.
If it asks whether to allow incoming connections, click **Allow**.

It prints the Mac's address and a 6-digit pairing code. Leave it running.

## 2. On Windows

Optional: start **MySQL** in the XAMPP Control Panel so the databases are exported too.

```
cd C:\Users\HP\Desktop\mac-transfer
python send.py --dry-run     # see sizes first
python send.py               # type the Mac address and pairing code
```

The first time, Windows may ask whether Python can use the network. Allow it on private networks.

## Result on the Mac

```
~/Desktop/from-windows/
  ap/  gigs/  my job(geeks)/  htdocs/
  databases/xampp-databases.sql
```

- If anything stops partway, run `send.py` again. Files already copied are skipped.
- `node_modules`, `vendor` (when `composer.json` is present), `.next`, `.expo`, Python
  venvs and Android build output are not copied. Run `npm install` / `composer install` on the Mac.
  Use `--everything` to copy them anyway.
- Import the databases into MySQL on the Mac (XAMPP for Mac, MAMP or Homebrew MySQL):
  `mysql -u root < ~/Desktop/from-windows/databases/xampp-databases.sql`
