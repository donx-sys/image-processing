# Hands-On Learning — Digital Image Processing

Interactive Python tools for learning Digital Image Processing — from
pixels to segmentation, hands-on.

Each topic opens in its own window with a manual page explaining the
concept underneath.

---

## What's inside

| # | Topic | Tool |
|---|---|---|
| 1.1 | Understanding Matrix Representation | `image_representation.py` |
| 2.1.1 | Spatial Resolution: Resize | `image_resizer.py` |
| 2.1.2 | Spatial Resolution: Cropping | `cropping_gui.py` |
| 2.2.1 | Intensity Resolution: Quantization | `intensity_gui.py` |
| 3.1 | Preprocessing: Noise Removal | `noise_gui.py` |
| 3.2 | Preprocessing: Contrast Enhancement | `contrast_gui.py` |
| 3.3 | Preprocessing: Information-Rich Areas | `information_gui.py` |
| 4.1 | Segmentation Methods | `segmentation_gui.py` |
| 4.2 | Boolean Operations on Images | `boolean_gui.py` |

---

## Windows

### 1. Install Python

Download Python 3.10 or newer from
<https://www.python.org/downloads/>.

During the installer, **tick the box that says "Add python.exe to
PATH"**. Skip this and nothing else will work.

### 2. Open a terminal in the project folder

Open PowerShell (or Command Prompt) and `cd` into the folder that
contains `main.py`:

```powershell
cd path\to\handsondip
```

### 3. Create a virtual environment

```powershell
python -m venv venv
```

### 4. Activate it

**PowerShell:**

```powershell
.\venv\Scripts\Activate.ps1
```

If PowerShell refuses to run the script, run this once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

**Command Prompt:**

```cmd
venv\Scripts\activate.bat
```

### 5. Install the dependencies

```powershell
pip install pillow numpy scipy tabulate
```

### 6. Run

```powershell
python src\main.py
```

---

## macOS

### 1. Install Python

Check whether you already have it:

```bash
python3 --version
```

If the version is below 3.10 (or the command isn't found), install
Python with Homebrew:

```bash
brew install python-tk
```

If Homebrew isn't installed, get it first from <https://brew.sh>.

### 2. Open a terminal in the project folder

```bash
cd ~/path/to/handsondip
```

### 3. Create a virtual environment

```bash
python3 -m venv venv
```

### 4. Activate it

```bash
source venv/bin/activate
```

Your prompt should now start with `(venv)`.

### 5. Install the dependencies

```bash
pip install pillow numpy scipy tabulate
```

### 6. Run

```bash
python src/main.py
```

---

## Linux

### 1. Install Python, Tkinter, and venv tooling

Tkinter is a system package on Linux, not a pip one — install it before
anything else.

**Debian / Ubuntu / Pop!_OS:**

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip python3-tk
```

**Fedora / RHEL:**

```bash
sudo dnf install python3 python3-pip python3-tkinter
```

**Arch:**

```bash
sudo pacman -S python python-pip tk
```

### 2. Open a terminal in the project folder

```bash
cd ~/path/to/handsondip
```

### 3. Create a virtual environment

```bash
python3 -m venv venv
```

### 4. Activate it

```bash
source venv/bin/activate
```

Your prompt should now start with `(venv)`.

### 5. Install the dependencies

```bash
pip install pillow numpy scipy tabulate
```

### 6. Run

```bash
python src/main.py
```

---

## Using the launcher

- **Click a topic** to open that tool in its own window.
- **Click Docs** next to a topic to open its manual page.
- **Close a tool window** to return to the launcher.
- Inside a tool, **File → Back to Menu** returns to the launcher
  without closing the window.

Any files a tool saves — CSVs, PNGs — land in the folder you launched
`main.py` from.

---

## If something goes wrong

**`ModuleNotFoundError: No module named 'PIL'` (or numpy, scipy, tabulate)**
The virtual environment isn't active, or the pip install step was
skipped. Activate the venv and re-run the `pip install` line.

**`ModuleNotFoundError: No module named 'tkinter'` on Linux**
Install the system package for your distribution (see step 1 above).

**Window appears blank, or the Docs button does nothing**
Run `main.py` from a terminal, not by double-clicking. The lines it
prints at startup show the exact paths it's looking for.

**A tool opens and immediately closes**
Run that tool directly to see the traceback, e.g.
`python src/noise_gui.py`. The error names the missing module.
