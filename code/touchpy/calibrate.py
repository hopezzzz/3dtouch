"""Calibrate the Touch by resting the stylus in the inkwell.

The arm's encoders are incremental, so the driver has no idea where the
arm is until it sees it in a pose it recognises. The inkwell is that pose:
drop the stylus in, and the driver zeroes from there.

Until this is done, positions are offset by however far the arm happened
to be from the inkwell at power-on, and forces point the wrong way.

    python calibrate.py

This does the same job as the calibration step in Touch_SmartSetup.exe.
Run either one; they write the same calibration.
"""

from __future__ import annotations

import os
import sys
import time

from touch_hd import HDError, TouchDevice


def smart_setup_path() -> str:
    """Where Touch_SmartSetup.exe most likely is.

    It ships with the driver, so look next to the hd.dll that touch_hd
    actually loaded rather than guessing at an install path.
    """
    import touch_hd
    driver_dir = os.path.dirname(getattr(touch_hd._hd, "_name", "") or "")
    candidate = os.path.join(driver_dir, "Touch_SmartSetup.exe")
    if driver_dir and os.path.isfile(candidate):
        return candidate
    return "Touch_SmartSetup.exe（在驱动安装目录里）"

GREEN, YELLOW, DIM, RESET = "\033[32m", "\033[33m", "\033[2m", "\033[0m"
TIMEOUT_S = 120.0


def main():
    try:
        dev = TouchDevice().open()
    except (HDError, RuntimeError) as exc:
        print(f"Could not open the device:\n  {exc}", file=sys.stderr)
        return 1

    try:
        styles = dev.calibration_style_names()
        print(f"device: {dev.model}  s/n {dev.serial_number}")
        print(f"calibration style: {', '.join(styles) or 'unknown'}")

        status = dev.calibration_status()
        if status == "ok":
            print(f"\n{GREEN}Already calibrated.{RESET} Nothing to do.")
            return 0

        if "inkwell" in styles:
            print(f"\n{YELLOW}Put the stylus in the inkwell{RESET} "
                  f"(the cradle on the base) and leave it there.")
        else:
            print(f"\n{YELLOW}Move the arm through its full range{RESET} "
                  f"until calibration completes.")
        print(f"{DIM}Waiting up to {TIMEOUT_S:.0f}s. Ctrl+C to give up.{RESET}\n")

        started = time.perf_counter()
        last_status = None
        while True:
            status = dev.calibration_status()
            elapsed = time.perf_counter() - started

            if status != last_status:
                print(f"  [{elapsed:5.1f}s] {status}")
                last_status = status

            if status == "ok":
                pos = dev.read().position
                print(f"\n{GREEN}Calibrated.{RESET}  "
                      f"position now {tuple(round(v, 2) for v in pos)} mm")
                print("\nNext:  python demo_read.py")
                return 0

            if status == "needs_update":
                # The driver has a correction ready and is waiting to be
                # told to apply it -- that only happens once the arm is
                # actually in the recognised pose.
                try:
                    dev.update_calibration()
                except HDError:
                    # Not in the pose yet; keep waiting.
                    pass
            elif status == "needs_manual_input":
                print(f"\n{YELLOW}This device wants the manual routine.{RESET}")
                print("Run Touch_SmartSetup.exe and follow its instructions:")
                print(f"  {smart_setup_path()}")
                return 1

            if elapsed > TIMEOUT_S:
                print(f"\n{YELLOW}Timed out{RESET} with status '{status}'.")
                print("Try Touch_SmartSetup.exe instead:")
                print(f"  {smart_setup_path()}")
                return 1

            time.sleep(0.25)

    except KeyboardInterrupt:
        print("\ncancelled.")
        return 1
    finally:
        dev.close()


if __name__ == "__main__":
    sys.exit(main())
