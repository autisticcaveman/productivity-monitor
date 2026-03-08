# Productivity Monitor — Multi-Machine Deployment Guide

This guide walks through copying the Productivity Monitor to a second Mac from scratch.
Every step is written out in full. No prior experience with terminals, SSH, or programming is assumed.

---

## System Requirements

### Source Machine (the Mac you're copying FROM)
- macOS 12 Ventura or newer
- Python 3.9 or newer (check: open Terminal, type `python3 --version`, press Enter)
- The productivity monitor already installed and working

### Destination Machine (the Mac you're copying TO)
- macOS 12 Ventura or newer
- Python 3 — comes pre-installed on all modern Macs. Confirm it:
  - Open Terminal on the new Mac
  - Type `python3 --version` and press Enter
  - If you see a version number (e.g. `Python 3.9.6`), you're good
  - If you see "command not found": install Xcode Command Line Tools by typing `xcode-select --install` and following the prompts
- Both Macs must be on the same network OR the destination Mac must be reachable over the internet
- The same user account name should exist on both machines

### Optional — Recommendation sync
If you want tool and workflow recommendations to be shared between both machines, you need a folder that both machines can read and write. This can be:
- A cloud-synced folder (iCloud Drive, Dropbox, OneDrive, etc.)
- A network share
- An Obsidian vault synced between machines

If you don't have a shared folder, recommendations are seeded from defaults on each machine independently — this is fine.

---

## Overview

Before diving in, here's what these steps accomplish:

1. Set up password-free SSH login between the two Macs
2. Tell the deploy script the address of the new Mac
3. One script copies all files and runs the installer on the remote automatically
4. Optionally import shared recommendations
5. Grant one macOS permission so the monitor can see which app is in focus

Total time: approximately 15–25 minutes.

---

## Part 1 — Find the New Mac's Address

You need the network address of the destination Mac.

### Option A: Use the Mac's hostname (easier, works on home networks)

1. On the **destination Mac**, click the Apple menu (&#63743;) → **System Settings**
2. Click **General** → **Sharing**
3. Look for **Local Hostname** — it will look like `someones-macbook-pro.local`
4. Write this down

### Option B: Use the IP address (more reliable on all networks)

1. On the **destination Mac**, click the Apple menu (&#63743;) → **System Settings**
2. Click **Wi-Fi** (or **Network**) → **Details** next to your connected network
3. Look for the **IP Address** line — it will look like `192.168.1.45`
4. Write this down

> Try the hostname first (Option A). If connection fails later, come back and use the IP address.

---

## Part 2 — Enable Remote Login on the New Mac

1. On the **destination Mac**: Apple menu (&#63743;) → **System Settings** → **General** → **Sharing**
2. Find **Remote Login** and toggle it **ON**
3. Next to "Allow access for:", select **All users**
4. You should see a confirmation line like:
   ```
   To log in to this computer remotely, type "ssh yourusername@192.168.1.45"
   ```

---

## Part 3 — Edit the Deploy Config

Switch to your **source Mac**.

1. Open **Terminal** (`Command + Space` → type `Terminal` → Enter)

2. Open the config file:
   ```bash
   open -e /path/to/productivity-monitor/.deployrc
   ```
   Replace `/path/to/productivity-monitor` with wherever you cloned the repo.

3. The file looks like this:
   ```
   REMOTE_HOST=""
   REMOTE_PATH="/Users/yourusername/productivity-monitor"
   VAULT_PATH="/path/to/shared/folder"
   ```

4. Fill in `REMOTE_HOST` with the address from Part 1:
   - Hostname: `REMOTE_HOST="yourusername@someones-macbook-pro.local"`
   - IP address: `REMOTE_HOST="yourusername@192.168.1.45"`

5. Set `REMOTE_PATH` to where you want the files on the destination Mac
   (default is fine if you're not sure)

6. If you have a shared folder for recommendation sync, set `VAULT_PATH` to its path.
   Leave blank to skip sync.

7. Save and close.

---

## Part 4 — Set Up Password-Free SSH Login

This creates a key pair so the source Mac can connect to the destination without a password every time. Do this once.

1. On the **source Mac**, check if you already have an SSH key:
   ```bash
   ls ~/.ssh/id_ed25519.pub
   ```
   - If you see a path printed: you already have one — **skip to step 3**
   - If you see "No such file": continue to step 2

2. Create a new SSH key (press Enter to accept all prompts, no passphrase needed):
   ```bash
   ssh-keygen -t ed25519
   ```

3. Copy your key to the destination Mac:
   ```bash
   ssh-copy-id yourusername@someones-macbook-pro.local
   ```
   - Type `yes` if asked about connecting
   - Enter the **destination Mac's login password** when asked
   - You should see: `Number of key(s) added: 1`

4. Test the connection — this should connect **without asking for a password**:
   ```bash
   ssh yourusername@someones-macbook-pro.local "echo Connection successful"
   ```

---

## Part 5 — Run the Deploy Script

```bash
bash /path/to/productivity-monitor/deploy.sh
```

The script will:
- Verify the SSH connection
- Copy all project files to the destination Mac
- SSH in and run `install.py` automatically
- Export your recommendations to the sync folder (if configured)

At the end you should see:
```
══════════════════════════════════════════════
  Deploy complete.
  Dashboard will be at http://localhost:5555
  on the remote machine.
══════════════════════════════════════════════
```

---

## Part 6 — Import Recommendations (optional)

If you configured a sync folder, import the recommendations on the destination Mac:

1. On the **destination Mac**, open Terminal
2. Run:
   ```bash
   python3 /path/to/productivity-monitor/sync.py import
   ```

You should see:
```
Imported from source-mac (exported 2026-03-08T17:11:27)
Added: 9  |  Already present: 0
```

---

## Part 7 — Grant Accessibility Permission on the New Mac

Without this, the monitor runs but can't read app names — everything shows as "unknown".

1. Apple menu (&#63743;) → **System Settings** → **Privacy & Security** → **Accessibility**
2. Click the **+** button
3. Navigate to **Applications** → select **Terminal** (or iTerm2 if that's what you use)
4. Ensure the toggle next to Terminal is **ON**

App names will appear in the dashboard within 30 seconds of the next poll.

---

## Part 8 — Verify Everything is Working

1. On the **destination Mac**, open a browser and go to: **http://localhost:5555**
2. You should see the Productivity Dashboard
3. The **green pulsing dot** in the top-left confirms the monitor is running
4. The "Active Right Now" section should show an app name (not "unknown")

To confirm the services will auto-restart after a reboot:
```bash
launchctl list | grep productivity-monitor
```
You should see two entries — `com.productivity-monitor.daemon` and `com.productivity-monitor.dashboard`.

---

## Keeping Both Machines in Sync

### Updating code (when changes are made on the source machine)

```bash
bash /path/to/productivity-monitor/deploy.sh
```

Only code is synced — your activity database on the destination is never touched.

### Syncing recommendations

**Source → destination:**
```bash
# On source machine:
python3 sync.py export

# On destination machine:
python3 sync.py import
```

**Destination → source:**
```bash
# On destination machine:
python3 sync.py export

# On source machine:
python3 sync.py import
```

**Check what's in the sync file:**
```bash
python3 sync.py status
```

---

## Stopping or Uninstalling

```bash
python3 /path/to/productivity-monitor/uninstall.py
```

This stops the background services and removes auto-start entries.
Your activity data is preserved — delete the `data_dir` folder manually if you want a clean slate.

---

## Troubleshooting

### "Connection refused" or SSH fails
Remote Login is not enabled — go back to Part 2.

### "Permission denied (publickey)"
The SSH key wasn't copied successfully — redo Part 4, step 3.

### Dashboard shows "Monitor not running"
Re-run the installer on the destination Mac:
```bash
python3 /path/to/productivity-monitor/install.py --defaults
```

### App shows as "unknown" in the dashboard
Accessibility permission wasn't granted — go back to Part 7. If Terminal is already listed, remove it and re-add it, then wait 60 seconds.

### "python3: command not found" on the destination Mac
```bash
xcode-select --install
```
Follow the prompts, then re-run `install.py`.

### Dashboard isn't loading at http://localhost:5555
Check the error log (path shown in `config.json` → `data_dir`):
```bash
cat /path/to/data/dashboard-err.log
```
Then restart:
```bash
python3 /path/to/productivity-monitor/install.py --defaults
```

---

## File Reference

| File | What it does |
|------|-------------|
| `monitor.py` | Background process — watches active apps, reloads config/categories on every poll |
| `dashboard/app.py` | Web server — dashboard + Settings API at http://localhost:5555 |
| `categories.json` | Maps app names to productivity categories (editable via ⚙ Settings panel) |
| `analyze.py` | Generates insights from activity data (runs hourly) |
| `install.py` | Cross-platform installer (macOS / Linux / Windows) |
| `uninstall.py` | Removes background services |
| `sync.py` | Syncs recommendations via shared folder |
| `deploy.sh` | Pushes code to a remote Mac via rsync + SSH, runs `install.py --defaults` on remote |
| `.deployrc` | Your remote host address and paths — **never committed to git** |
| `config.json` | Settings: data directory, port, poll interval, sync path, auto_categorize |
| `VERSION` | Current version number |
| `data/` | Your activity database and logs — **never committed to git** |
