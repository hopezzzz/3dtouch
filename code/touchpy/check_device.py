"""Diagnose a Touch that will not come up.

Works from the outside in: is the driver installed, does Windows see the
device on USB, and only then does the HD API agree to open it.  Each stage
prints what it found, so the first stage that fails tells you where the
problem actually is.

    python check_device.py            # one pass
    python check_device.py --watch    # keep watching; plug/unplug and see
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

# 3D Systems' USB vendor ID. The product ID says which device and,
# importantly, which generation of firmware:
VENDOR_ID = "2988"
PRODUCT_IDS = {
    "0301": "Touch (USB, CDC serial firmware)",
    "0302": "Geomagic Touch (USB, CDC serial firmware)",
    "0303": "Touch X (USB, CDC serial firmware)",
    "0304": "Touch (USB, HID firmware)",
}

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
)


def enable_ansi():
    """Turn on VT escape processing so the colours above render in cmd.exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # -11 is STD_OUTPUT_HANDLE; 0x4 is ENABLE_VIRTUAL_TERMINAL_PROCESSING.
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x4)
    except Exception:
        pass


def ps(script: str) -> str:
    """Run a PowerShell snippet and return stdout."""
    # Device names are localised, so force UTF-8 out of PowerShell rather
    # than letting it fall back to the console's ANSI code page.
    script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + script
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=60,
        )
        return out.stdout.decode("utf-8", "replace").strip()
    except (subprocess.SubprocessError, OSError) as exc:
        return f"<powershell failed: {exc}>"


def ok(msg):
    print(f"  {GREEN}[ok]{RESET}   {msg}")


def bad(msg):
    print(f"  {RED}[FAIL]{RESET} {msg}")


def warn(msg):
    print(f"  {YELLOW}[warn]{RESET} {msg}")


def note(msg):
    print(f"         {DIM}{msg}{RESET}")


# ---------------------------------------------------------------- stage 1

def check_driver() -> bool:
    print("\n[1] Touch device driver")
    installed = ps(
        r"Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',"
        r"'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' "
        r"-ErrorAction SilentlyContinue | "
        r"Where-Object { $_.DisplayName -match 'Phantom Device Drivers|Touch Device Driver' } | "
        r"ForEach-Object { $_.DisplayName + ' ' + $_.DisplayVersion }"
    )
    if installed:
        for line in installed.splitlines():
            ok(f"installed: {line.strip()}")
        return True
    bad("no Touch/Phantom device driver found in the uninstall registry")
    note("Install Touch_Device_Driver_*.exe from 3D Systems first.")
    return False


# ---------------------------------------------------------------- stage 2

def find_devices():
    """Return (present, absent) lists of 3D Systems devices Windows knows."""
    raw = ps(
        "Get-PnpDevice | Where-Object { $_.InstanceId -match 'VID_%s' } | "
        "ForEach-Object { $_.Status + '|' + $_.Class + '|' + $_.FriendlyName + '|' + $_.InstanceId }"
        % VENDOR_ID
    )
    present, absent = [], []
    for line in raw.splitlines():
        parts = line.strip().split("|")
        if len(parts) < 4:
            continue
        status, cls, name, instance = parts[0], parts[1], parts[2], "|".join(parts[3:])
        (present if status == "OK" else absent).append((status, cls, name, instance))
    return present, absent


def describe(instance: str) -> str:
    for pid, label in PRODUCT_IDS.items():
        if f"PID_{pid}" in instance.upper():
            return label
    return "unknown 3D Systems device"


def check_usb() -> bool:
    print("\n[2] USB enumeration")
    present, absent = find_devices()

    if present:
        for _status, cls, name, instance in present:
            ok(f"{describe(instance)}")
            note(f"class={cls}  {instance}")
        return True

    bad(f"no VID_{VENDOR_ID} device is currently present on USB")

    if absent:
        note("Windows has seen these before, so the hardware has worked here:")
        for status, cls, name, instance in absent:
            note(f"  ({status}) {describe(instance)}  {instance}")

    # A device failing before it can report its VID/PID shows up with a
    # zeroed hardware ID -- that is a physical-layer failure, not a
    # missing driver, and no amount of reinstalling will fix it.
    broken = ps(
        "Get-PnpDevice -PresentOnly | Where-Object { $_.Status -ne 'OK' } | "
        "ForEach-Object { $_.FriendlyName + '|' + $_.InstanceId + '|' + $_.ProblemDescription }"
    )
    hits = [ln for ln in broken.splitlines() if "DEVICE_DESCRIPTOR" in ln.upper()
            or "VID_0000" in ln.upper()]
    if hits:
        print()
        warn("there is a USB device failing before it can identify itself:")
        for ln in hits:
            note(ln.strip())
        note("")
        note("A zeroed VID/PID means Windows could not read the USB descriptor")
        note("at all. That is a cable/port/power fault, not a driver problem:")
        note("  1. unplug USB")
        note("  2. unplug the power adapter, wait 10s, plug it back in")
        note("  3. plug USB into a port directly on the machine, not a hub")
        note("  4. if it persists, try a different USB cable")
    return False


# ---------------------------------------------------------------- stage 3

def check_hd_api() -> bool:
    print("\n[3] OpenHaptics HD API")
    try:
        import touch_hd
    except RuntimeError as exc:
        bad(str(exc))
        return False
    ok(f"hd.dll loaded from {touch_hd._hd._name}")

    try:
        dev = touch_hd.TouchDevice().open()
    except touch_hd.HDError as exc:
        bad(f"hdInitDevice failed: {exc}")
        note("If USB enumeration above passed, run Touch_SmartSetup.exe once")
        note("to calibrate the device and save a configuration.")
        return False

    try:
        for key, value in dev.info().items():
            ok(f"{key}: {value}")
        cal = dev.calibration_status()
        (ok if cal == "ok" else warn)(f"calibration: {cal}")
        if cal != "ok":
            note("Put the stylus in the inkwell, or run Touch_SmartSetup.exe.")
        state = dev.read()
        ok(f"position: {tuple(round(v, 2) for v in state.position)} mm")
        ok(f"servo loop: {state.update_rate:.0f} Hz")
    finally:
        dev.close()
    return True


# ---------------------------------------------------------------- watch

def find_failed_devices():
    """USB devices that died before they could report a VID/PID."""
    raw = ps(
        "Get-PnpDevice -PresentOnly -Class USB | "
        "Where-Object { $_.Status -ne 'OK' } | "
        "ForEach-Object { $_.InstanceId }"
    )
    return [ln.strip() for ln in raw.splitlines()
            if "VID_0000" in ln.upper() or "DESCRIPTOR" in ln.upper()]


def watch():
    print("Watching USB. Plug and unplug the Touch now. Ctrl+C to stop.\n")
    print(f"{DIM}Watching two things:{RESET}")
    print(f"{DIM}  - any VID_{VENDOR_ID} device coming online (what we want){RESET}")
    print(f"{DIM}  - any device failing to enumerate. If one of those appears and{RESET}")
    print(f"{DIM}    disappears in step with your plugging, that IS the Touch, and{RESET}")
    print(f"{DIM}    the fault is the cable, the port, or the power adapter.{RESET}\n")

    last = None
    try:
        while True:
            present, _ = find_devices()
            failed = find_failed_devices()
            key = (tuple(sorted(i for _s, _c, _n, i in present)), tuple(sorted(failed)))

            if key != last:
                stamp = time.strftime("%H:%M:%S")
                if present:
                    for _s, cls, _n, instance in present:
                        print(f"{stamp} {GREEN}+ ONLINE{RESET}   {describe(instance)}")
                        print(f"         {DIM}{cls}  {instance}{RESET}")
                else:
                    print(f"{stamp} {RED}- OFFLINE{RESET}  no VID_{VENDOR_ID} device present")
                for instance in failed:
                    print(f"{stamp} {YELLOW}! FAILED{RESET}   enumeration failed: {instance}")
                last = key
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nstopped.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true",
                        help="poll continuously instead of running one pass")
    args = parser.parse_args()

    enable_ansi()

    if sys.platform != "win32":
        print("This diagnostic uses PowerShell and only runs on Windows.")
        return 2

    if args.watch:
        watch()
        return 0

    print("=" * 62)
    print(" 3D Systems Touch - connection diagnostic")
    print("=" * 62)

    if not check_driver():
        return 1
    if not check_usb():
        print(f"\n{RED}Stopped:{RESET} the device is not on the USB bus, so the HD API")
        print("cannot open it. Fix the connection first, then re-run.")
        return 1
    if not check_hd_api():
        return 1

    print(f"\n{GREEN}All checks passed.{RESET} Try:  python demo_read.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
