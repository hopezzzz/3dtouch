"""Live readout of the Touch: position, orientation, joints, buttons.

    python demo_read.py                 # live display, 60 Hz
    python demo_read.py --rate 200      # poll faster
    python demo_read.py --csv log.csv   # also append samples to a CSV

Move the stylus and press its two buttons. Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time

from touch_hd import HDError, TouchDevice

CLEAR_HOME = "\033[H\033[J"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
BOLD, DIM, GREEN, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[0m"


def bar(value, lo, hi, width=28):
    """A one-line gauge, so you can see an axis move without reading digits."""
    span = hi - lo
    frac = 0.0 if span == 0 else (value - lo) / span
    frac = min(max(frac, 0.0), 1.0)
    filled = int(round(frac * (width - 1)))
    return "[" + "-" * filled + "|" + "-" * (width - 1 - filled) + "]"


def render(state, info, samples, elapsed):
    x, y, z = state.position
    lo = info["usable_workspace_mm"][:3]
    hi = info["usable_workspace_mm"][3:]

    lines = [
        f"{BOLD}3D Systems Touch{RESET}  {DIM}{info['model']} "
        f"s/n {info['serial_number']}{RESET}",
        "",
        f"  {BOLD}position{RESET} (mm)",
        f"    X {x:9.3f}  {bar(x, lo[0], hi[0])}",
        f"    Y {y:9.3f}  {bar(y, lo[1], hi[1])}",
        f"    Z {z:9.3f}  {bar(z, lo[2], hi[2])}",
        "",
        "  {}velocity{} (mm/s)   {:8.1f} {:8.1f} {:8.1f}".format(
            BOLD, RESET, *state.velocity),
        "",
        "  {}joint angles{} (deg)  {:7.2f} {:7.2f} {:7.2f}".format(
            BOLD, RESET, *[math.degrees(a) for a in state.joint_angles]),
        "  {}gimbal angles{} (deg) {:7.2f} {:7.2f} {:7.2f}".format(
            BOLD, RESET, *[math.degrees(a) for a in state.gimbal_angles]),
    ]

    rot = state.orientation
    if rot:
        lines.append("")
        lines.append(f"  {BOLD}orientation{RESET} (rotation matrix)")
        for row in rot:
            lines.append("    {:7.4f} {:7.4f} {:7.4f}".format(*row))

    down = state.buttons_down
    if down:
        pressed = " ".join(f"{GREEN}[{n}]{RESET}" for n in down)
    else:
        pressed = f"{DIM}none{RESET}"
    lines += [
        "",
        f"  {BOLD}buttons{RESET} {pressed}   {DIM}(raw 0b{state.buttons:04b}){RESET}",
        "",
        f"  {DIM}servo {state.update_rate:6.0f} Hz | polled {samples} samples "
        f"in {elapsed:.1f}s ({samples / max(elapsed, 1e-9):5.1f} Hz){RESET}",
        "",
        f"  {DIM}Ctrl+C to stop{RESET}",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate", type=float, default=60.0,
                        help="polls per second (default 60)")
    parser.add_argument("--csv", metavar="PATH",
                        help="append samples to this CSV file")
    parser.add_argument("--raw", action="store_true",
                        help="print one line per sample instead of a live display")
    args = parser.parse_args()

    period = 1.0 / args.rate

    try:
        dev = TouchDevice().open()
    except (HDError, RuntimeError) as exc:
        print(f"Could not open the device:\n  {exc}\n", file=sys.stderr)
        print("Run  python check_device.py  to find out which stage is failing.",
              file=sys.stderr)
        return 1

    writer = None
    csv_file = None
    if args.csv:
        csv_file = open(args.csv, "a", newline="", encoding="utf-8")
        writer = csv.writer(csv_file)
        if csv_file.tell() == 0:
            writer.writerow([
                "t", "x_mm", "y_mm", "z_mm",
                "vx", "vy", "vz",
                "j1_rad", "j2_rad", "j3_rad",
                "g1_rad", "g2_rad", "g3_rad",
                "buttons",
            ])

    info = dev.info()
    cal = dev.calibration_status()
    if cal != "ok":
        print(f"note: calibration is '{cal}' -- put the stylus in the inkwell, "
              f"or run Touch_SmartSetup.exe once.\n")
        time.sleep(1.5)

    samples = 0
    started = time.perf_counter()
    next_tick = started

    if not args.raw:
        sys.stdout.write(HIDE_CURSOR)
    try:
        while True:
            state = dev.read()
            samples += 1
            now = time.perf_counter()
            elapsed = now - started

            if writer:
                writer.writerow(
                    [f"{elapsed:.6f}"]
                    + [f"{v:.6f}" for v in state.position]
                    + [f"{v:.6f}" for v in state.velocity]
                    + [f"{v:.6f}" for v in state.joint_angles]
                    + [f"{v:.6f}" for v in state.gimbal_angles]
                    + [state.buttons]
                )

            if args.raw:
                print("{:8.3f}  {:9.3f} {:9.3f} {:9.3f}  btn={:04b}".format(
                    elapsed, *state.position, state.buttons))
            else:
                sys.stdout.write(CLEAR_HOME + render(state, info, samples, elapsed))
                sys.stdout.flush()

            next_tick += period
            sleep = next_tick - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)
            else:
                # Fell behind; resync rather than spiral.
                next_tick = time.perf_counter()
    except KeyboardInterrupt:
        pass
    finally:
        if not args.raw:
            sys.stdout.write(SHOW_CURSOR + "\n")
        dev.close()
        if csv_file:
            csv_file.close()
            print(f"wrote {samples} samples to {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
