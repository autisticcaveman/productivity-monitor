# Productivity Monitor — Deployment Guide

This guide walks through copying the Productivity Monitor to a second Mac from scratch.
Every step is written out in full. No prior experience with terminals, SSH, or programming is assumed.

---

## System Requirements

### Source Machine (the Mac you're copying FROM — your-mac)
- macOS 12 Ventura or newer
- Python 3.9 or newer (check: open Terminal, type `python3 --version`, press Enter)
- The productivity monitor already installed and working

### Destination Machine (the Mac you're copying TO)
- macOS 12 Ventura or newer
- Python 3 — comes pre-installed on all modern Macs, but confirm it:
  - Open Terminal on the new Mac
  - Type `python3 --version` and press Enter
  - If you see a version number (e.g. `Python 3.9.6`), you're good
  - If you see "command not found": install Xcode Command Line Tools by typing `xcode-select --install` and following the prompts
- The Obsidian vault must already be synced and accessible at the same path as on your-mac
  - Default expected path: `~/your-sync-folder`
  - If your vault is somewhere else, you will update this in Step 3
- Both Macs must be on the same network OR the destination Mac must be reachable over the internet
- The same user account name (`chad`) should exist on both machines

---

## Overview of What's Happening

Before diving in, here's the plain-English version of what these steps accomplish:

1. You'll set up a "password-free login" between the two Macs using an SSH key (a pair of files that act like a lock and key)
2. You'll tell the deploy script the address of the new Mac
3. One script then copies all the files over and sets everything up automatically
4. You'll import your recommendations from the shared Obsidian vault onto the new Mac
5. You'll grant one macOS permission so the monitor can see which app is open

Total time: approximately 15–25 minutes.

---

## Part 1 — Find the New Mac's Address

You need the network address of the destination Mac. There are two ways to get it.

### Option A: Use the Mac's hostname (easier, works on home networks)

1. On the **destination Mac**, click the Apple menu () in the top-left corner
2. Click **System Settings**
3. Click **General** in the left sidebar
4. Click **Sharing**
5. Look for the line that says **"Local Hostname"** — it will look something like `chads-macbook-pro.local`
6. Write this down — you will use it in Step 3

### Option B: Use the IP address (more reliable, works on all networks)

1. On the **destination Mac**, click the Apple menu ()
2. Click **System Settings**
3. Click **Wi-Fi** (or **Network**) in the left sidebar
4. Click the **Details** button next to your connected network
5. Look for the **IP Address** line — it will look something like `192.168.1.45`
6. Write this down — you will use it in Step 3

> **Which to use?** Try the hostname first (Option A). If it doesn't work later, come back and use the IP address (Option B).

---

## Part 2 — Enable Remote Login on the New Mac

The new Mac needs to allow SSH connections (the technology used to copy files and run commands remotely).

1. On the **destination Mac**, click the Apple menu ()
2. Click **System Settings**
3. Click **General** in the left sidebar
4. Click **Sharing**
5. Find **Remote Login** in the list
6. Toggle it **ON** (the toggle turns green)
7. Next to "Allow access for:", select **All users** (or make sure your user `chad` is listed)
8. You should see a line that says something like:
   ```
   To log in to this computer remotely, type "ssh yourusername@192.168.1.45"
   ```
   This confirms it's working. Note the address shown — this is what you'll use in Step 3.

---

## Part 3 — Edit the Deploy Config on your-mac

Now switch back to your **source Mac (your-mac)**.

1. Open **Terminal** (press `Command + Space`, type `Terminal`, press Enter)

2. Open the config file in a text editor by typing this command and pressing Enter:
   ```bash
   open -e ~/productivity-monitor/.deployrc
   ```
   This opens the file in TextEdit.

3. You will see a file that looks like this:
   ```
   REMOTE_HOST=""
   REMOTE_PATH="~/productivity-monitor"
   VAULT_PATH="~/your-sync-folder"
   ```

4. Fill in `REMOTE_HOST` with the address you found in Part 1. Examples:
   - Using hostname: `REMOTE_HOST="yourusername@your-mac.local"`
   - Using IP address: `REMOTE_HOST="yourusername@192.168.1.45"`

5. If your Obsidian vault on the new Mac is at a **different path** than `~/your-sync-folder`, update `VAULT_PATH` to match.

6. Leave `REMOTE_PATH` as-is unless you want the files in a different location.

7. Save the file: press `Command + S`, then close TextEdit.

---

## Part 4 — Set Up Password-Free SSH Login

This step creates a "key" on your-mac that lets it log into the new Mac automatically, without asking for a password every time. You only do this once.

1. On **your-mac**, in Terminal, check if you already have an SSH key:
   ```bash
   ls ~/.ssh/id_ed25519.pub
   ```
   - If you see a file path printed: you already have a key — **skip to step 3**
   - If you see "No such file or directory": continue to step 2

2. Create a new SSH key (press Enter to accept all defaults when asked — do **not** set a passphrase unless you know why you need one):
   ```bash
   ssh-keygen -t ed25519
   ```
   When it asks "Enter file in which to save the key": just press **Enter**
   When it asks "Enter passphrase": just press **Enter** (twice)

3. Copy your key to the new Mac (replace the address with your actual address from Part 1):
   ```bash
   ssh-copy-id yourusername@your-mac.local
   ```
   - It will ask: `Are you sure you want to continue connecting?` — type `yes` and press Enter
   - It will ask for the **password of the `chad` account on the new Mac** — type it and press Enter
   - You should see: `Number of key(s) added: 1`

4. Test that it worked — this should connect **without asking for a password**:
   ```bash
   ssh yourusername@your-mac.local "echo Connection successful"
   ```
   You should see: `Connection successful`

   If it still asks for a password, double-check that Remote Login is enabled on the new Mac (Part 2) and that the address is correct.

---

## Part 5 — Run the Deploy Script

Now the automated part. One command copies everything and sets it up on the new Mac.

1. On **your-mac**, in Terminal, run:
   ```bash
   bash ~/productivity-monitor/deploy.sh
   ```

2. The script will:
   - Verify the SSH connection
   - Copy all the project files to the new Mac (you'll see filenames scrolling by)
   - Connect to the new Mac and run the setup
   - Install Flask (a small web library) on the new Mac
   - Create and start the background services (monitor + dashboard)
   - Export your recommendations to the Obsidian vault

3. At the end you should see:
   ```
   ══════════════════════════════════════════════
     Deploy complete.
     Dashboard will be at http://localhost:5555
     on the remote machine.
   ```

   If you see any errors, see the **Troubleshooting** section at the bottom of this guide.

---

## Part 6 — Import Recommendations on the New Mac

The recommendations you've built up (tool suggestions, workflow tips) are stored in the shared Obsidian vault. Import them on the new Mac now.

1. On the **destination Mac**, open Terminal

2. Run:
   ```bash
   bash ~/productivity-monitor/vault-sync.sh import
   ```

3. You should see something like:
   ```
   Imported from your-mac.local (exported 2026-03-08T17:11:27)
   Added: 9  |  Already present: 0
   ```

---

## Part 7 — Grant Accessibility Permission on the New Mac

This is the most important post-install step. Without it, the monitor can see that *something* is running but not *what* app it is.

1. On the **destination Mac**, click the Apple menu ()
2. Click **System Settings**
3. Click **Privacy & Security** in the left sidebar
4. Scroll down and click **Accessibility**
5. Click the **+** (plus) button
6. Navigate to **Applications** → find and select **Terminal** (or **iTerm2** if that's what you use)
7. Make sure the toggle next to Terminal is turned **ON**

> You may be prompted to enter your Mac password to make changes. That's normal.

After granting this permission, the monitor will start seeing full app names and window titles within 30 seconds (its next poll cycle).

---

## Part 8 — Verify Everything is Working

1. On the **destination Mac**, open a browser (Safari, Chrome, Firefox — any)
2. Go to: **http://localhost:5555**
3. You should see the Productivity Dashboard

4. To confirm the monitor is actively tracking, check the top-left of the dashboard:
   - A **green pulsing dot** means the monitor is running and logging
   - The "Active Right Now" section should show an app name (not "unknown")
   - If it still shows "unknown", wait 1–2 minutes after granting Accessibility, then refresh

5. To verify the services will automatically restart if the Mac reboots, you can check:
   ```bash
   launchctl list | grep chad
   ```
   You should see two lines with `com.productivity-monitor.daemon` and `com.productivity-monitor.dashboard`

---

## Keeping the Two Machines in Sync

### Updating the code (if changes are made on your-mac)

Just re-run the deploy script from your-mac:
```bash
bash ~/productivity-monitor/deploy.sh
```
It only copies files — it does not erase your activity data on the remote.

### Syncing recommendations between machines

When new recommendations are added on either machine, share them via the vault:

**From your-mac to the new Mac:**
```bash
# On elas:
bash ~/productivity-monitor/vault-sync.sh export

# On new Mac:
bash ~/productivity-monitor/vault-sync.sh import
```

**From the new Mac to your-mac:**
```bash
# On new Mac:
bash ~/productivity-monitor/vault-sync.sh export

# On elas:
bash ~/productivity-monitor/vault-sync.sh import
```

### Check what's currently in the vault sync file
```bash
bash ~/productivity-monitor/vault-sync.sh status
```

---

## Stopping or Uninstalling

To stop the monitor and dashboard on any machine:
```bash
bash ~/productivity-monitor/uninstall.sh
```

This stops the background services and removes the auto-start entries. Your activity data in `data/activity.db` is preserved — delete that file manually if you want a clean slate.

---

## Troubleshooting

### "Connection refused" or "ssh: connect to host ... port 22: Connection refused"
- Remote Login is not enabled on the destination Mac — go back to Part 2

### "Permission denied (publickey)"
- The SSH key wasn't copied successfully — redo Part 4, step 3
- Make sure you're using the same username that exists on the remote Mac

### "No such file or directory" when running deploy.sh
- You may be in the wrong directory. Use the full path:
  ```bash
  bash ~/productivity-monitor/deploy.sh
  ```

### Dashboard shows "Monitor not running"
- The LaunchAgent may not have loaded. On the destination Mac, run:
  ```bash
  bash ~/productivity-monitor/install.sh
  ```

### App shows as "unknown" in the dashboard
- Accessibility permission wasn't granted or hasn't taken effect yet
- Go back to Part 7 and confirm Terminal has the toggle set to ON
- If Terminal is already listed, try removing it and re-adding it
- Wait 60 seconds and refresh the dashboard

### "python3: command not found" on the destination Mac
- Run this on the destination Mac to install the developer tools (includes Python):
  ```bash
  xcode-select --install
  ```
  Follow the on-screen prompts, then re-run `install.sh`

### Dashboard isn't loading at http://localhost:5555
- Check if the Flask process is running:
  ```bash
  ps aux | grep "dashboard/app.py" | grep -v grep
  ```
- If nothing shows, restart the services:
  ```bash
  bash ~/productivity-monitor/install.sh
  ```
- Check for errors in the log:
  ```bash
  cat ~/productivity-monitor/data/dashboard-err.log
  ```

### "flask: command not found" or Flask import error
- Flask may not have installed correctly. Run manually:
  ```bash
  pip3 install flask --break-system-packages
  ```
  Then restart:
  ```bash
  bash ~/productivity-monitor/install.sh
  ```

---

## File Reference

| File | What it does |
|------|-------------|
| `monitor.py` | Background process — watches active apps every 30 seconds |
| `dashboard/app.py` | Web server — serves the dashboard at http://localhost:5555 |
| `categories.json` | Maps app names to productivity categories |
| `analyze.py` | Generates insights from your activity data (runs hourly) |
| `install.sh` | Sets up and starts both background services |
| `uninstall.sh` | Stops both services and removes auto-start entries |
| `deploy.sh` | Copies everything to a remote Mac and sets it up |
| `vault-sync.sh` | Syncs recommendations between machines via Obsidian vault |
| `.deployrc` | Config: remote Mac address and paths |
| `data/activity.db` | Your activity database — never synced, machine-specific |
| `data/monitor.log` | Log of what the monitor is doing |
| `data/dashboard-err.log` | Dashboard error log — check here if something breaks |
