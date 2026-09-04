"""Force feedback demo: a virtual floor you can feel with the stylus.

Below y = 0 the device pushes back with a spring, so the plane feels solid.
Hold stylus button 1 to switch to a spring that pulls the tip toward the
centre of the workspace.

    python demo_force.py
    python demo_force.py --stiffness 0.4     # N/mm, stiffer wall

Safety: force is clamped well under the device's nominal maximum, and the
demo refuses to start until the stylus is resting still. If the arm ever
starts to buzz or push on its own, let go and press Ctrl+C -- force output
is cut on exit, including on error.
"""

from __future__ import annotations

import argparse
import math
import sys
import time

from touch_hd import HDError, TouchDevice

BOLD, DIM, GREEN, YELLOW, RESET = (
    "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[0m"
)
CLEAR_HOME = "\033[H\033[J"

# A spring stiff enough to feel like a surface but soft enough to stay
# stable at 1 kHz with a Python callback in the loop. Past roughly
# 0.6 N/mm this device buzzes instead of feeling solid.
DEFAULT_STIFFNESS = 0.25   # N/mm
MAX_FORCE = 3.0            # N, our own clamp; the device can do more


def clamp_magnitude(vec, limit):
    mag = math.sqrt(sum(c * c for c in vec))
    if mag <= limit or mag == 0.0:
        return vec, mag
    scale = limit / mag
    return tuple(c * scale for c in vec), mag


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stiffness", type=float, default=DEFAULT_STIFFNESS,
                        help=f"wall stiffness in N/mm (default {DEFAULT_STIFFNESS})")
    parser.add_argument("--floor", type=float, default=0.0,
                        help="height of the virtual floor in mm (default 0)")
    parser.add_argument("--rate", type=float, default=60.0,
                        help="how often the demo recomputes the force (default 60 Hz)")
    args = parser.parse_args()

    if args.stiffness <= 0 or args.stiffness > 0.6:
        print("stiffness must be in (0, 0.6] N/mm -- higher values make this "
              "device buzz rather than feel solid.", file=sys.stderr)
        return 2

    try:
        dev = TouchDevice().open()
    except (HDError, RuntimeError) as exc:
        print(f"Could not open the device:\n  {exc}\n", file=sys.stderr)
        print("Run  python check_device.py  first.", file=sys.stderr)
        return 1

    period = 1.0 / args.rate

    try:
        info = dev.info()
        cal = dev.calibration_status()
        if cal != "ok":
            print(f"Calibration is '{cal}'. Forces will point the wrong way "
                  f"until the device is calibrated.\n"
                  f"Put the stylus in the inkwell, or run Touch_SmartSetup.exe.")
            return 1

        # Don't start pushing while someone is mid-motion.
        print("Let go of the stylus...", end="", flush=True)
        still_since = None
        while True:
            speed = math.sqrt(sum(v * v for v in dev.read().velocity))
            now = time.perf_counter()
            if speed < 5.0:
                still_since = still_since or now
                if now - still_since > 0.5:
                    break
            else:
                still_since = None
            time.sleep(0.02)
        print(" ok\n")

        dev.enable_force_output()

        started = time.perf_counter()
        next_tick = started
        peak = 0.0

        while True:
            state = dev.read()
            x, y, z = state.position
            hold = state.button(1)

            if hold:
                # Spring toward the workspace centre.
                lo = info["usable_workspace_mm"][:3]
                hi = info["usable_workspace_mm"][3:]
                centre = tuple((lo[i] + hi[i]) / 2.0 for i in range(3))
                force = tuple(
                    -args.stiffness * 0.5 * (p - c)
                    for p, c in zip(state.position, centre)
                )
                mode = f"{GREEN}spring to centre{RESET}"
            elif y < args.floor:
                # Penetration depth times stiffness, pushing back up.
                force = (0.0, args.stiffness * (args.floor - y), 0.0)
                mode = f"{GREEN}touching the floor{RESET}"
            else:
                force = (0.0, 0.0, 0.0)
                mode = f"{DIM}free space{RESET}"

            force, requested = clamp_magnitude(force, MAX_FORCE)
            dev.set_force(*force)

            mag = math.sqrt(sum(c * c for c in force))
            peak = max(peak, mag)

            clipped = f"  {YELLOW}(clamped from {requested:.2f} N){RESET}" if requested > MAX_FORCE else ""
            sys.stdout.write(
                CLEAR_HOME
                + f"{BOLD}Touch force feedback demo{RESET}\n\n"
                f"  virtual floor at y = {args.floor:.1f} mm, "
                f"stiffness {args.stiffness:.2f} N/mm\n\n"
                f"  position  {x:9.3f} {y:9.3f} {z:9.3f}  mm\n"
                f"  force     {force[0]:9.3f} {force[1]:9.3f} {force[2]:9.3f}  N"
                f"  (|F| {mag:5.2f}, peak {peak:5.2f}){clipped}\n\n"
                f"  state     {mode}\n"
                f"  buttons   {state.buttons_down or 'none'}\n\n"
                f"  {DIM}servo {state.update_rate:6.0f} Hz  "
                f"(should stay near 1000){RESET}\n\n"
                f"  {DIM}Move the stylus down until it stops. "
                f"Hold button 1 for the spring. Ctrl+C to quit.{RESET}"
            )
            sys.stdout.flush()

            next_tick += period
            sleep = next_tick - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_tick = time.perf_counter()

    except KeyboardInterrupt:
        pass
    finally:
        # Whatever happened, stop pushing before the handle goes away.
        try:
            dev.disable_force_output()
        finally:
            dev.close()
        print("\nforce output off.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
