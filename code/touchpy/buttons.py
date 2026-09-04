"""Live button state for the Touch stylus.

Shows which button bits are down right now, so you can work out which
physical button is which without guessing.

    python buttons.py            # live display
    python buttons.py --identify # guided: press one, then the other

The HD API reports buttons as a bitmask in HD_CURRENT_BUTTONS:
HD_DEVICE_BUTTON_1 is bit 0, HD_DEVICE_BUTTON_2 is bit 1. The Touch has
two; Touch X and the Phantom Premium models can report up to four.
"""

from __future__ import annotations

import argparse
import sys
import time

from touch_hd import BUTTON_MASKS, HDError, TouchDevice

BOLD, DIM, GREEN, YELLOW, RESET = (
    "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[0m"
)
CLEAR_HOME = "\033[H\033[J"
HIDE, SHOW = "\033[?25l", "\033[?25h"


def enable_ansi():
    if sys.platform != "win32":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetConsoleOutputCP(65001)
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, mode.value | 0x4)
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def live(dev, buttons_shown=2):
    """buttons_shown: how many to list; extras appear only once pressed."""
    print(HIDE, end="")
    try:
        while True:
            s = dev.read()
            rows = []
            for n, mask in sorted(BUTTON_MASKS.items()):
                if n > buttons_shown and not (s.buttons & mask):
                    continue
                down = bool(s.buttons & mask)
                box = f"{GREEN}[#]{RESET}" if down else f"{DIM}[ ]{RESET}"
                state = f"{GREEN}按下{RESET}" if down else f"{DIM}松开{RESET}"
                rows.append(f"    {box}  按钮 {n}   bit {mask.bit_length()-1}   {state}")
            sys.stdout.write(
                CLEAR_HOME
                + f"{BOLD}Touch 按钮状态{RESET}\n\n"
                + "\n".join(rows)
                + f"\n\n    {DIM}原始位掩码  0b{s.buttons:04b}  ({s.buttons}){RESET}\n"
                + f"    {DIM}笔尖位置    {s.position[0]:7.1f} {s.position[1]:7.1f} "
                  f"{s.position[2]:7.1f} mm{RESET}\n\n"
                + f"    {DIM}Ctrl+C 退出{RESET}"
            )
            sys.stdout.flush()
            time.sleep(1 / 60)
    except KeyboardInterrupt:
        pass
    finally:
        print(SHOW)


def wait_for_press(dev, timeout=30.0):
    """Block until a button goes down; return its mask, or 0 on timeout."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        buttons = dev.read().buttons
        if buttons:
            return buttons
        time.sleep(0.01)
    return 0


def wait_for_release(dev, timeout=30.0):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if not dev.read().buttons:
            return True
        time.sleep(0.01)
    return False


def identify(dev):
    print(f"\n{BOLD}按钮识别{RESET}\n")
    print("笔杆侧面有两个按钮，一前一后。")
    seen = {}

    for label, hint in (("前", "靠近笔尖的那个"), ("后", "靠近手掌的那个")):
        print(f"\n{YELLOW}请按住「{label}」按钮（{hint}），按住不放…{RESET}")
        wait_for_release(dev, timeout=5.0)
        mask = wait_for_press(dev)
        if not mask:
            print("  超时，没检测到按键")
            continue
        names = [n for n, m in BUTTON_MASKS.items() if mask & m]
        print(f"  {GREEN}检测到：按钮 {names}  位掩码 0b{mask:04b}{RESET}")
        seen[label] = (tuple(names), mask)
        print("  松开…")
        wait_for_release(dev)

    print(f"\n{BOLD}结果{RESET}")
    for label, (names, mask) in seen.items():
        print(f"  「{label}」按钮  ->  HD_DEVICE_BUTTON_{names[0]}  "
              f"(bit {mask.bit_length()-1}, 0b{mask:04b})")
    if len(seen) == 2:
        vals = [m for _n, m in seen.values()]
        if vals[0] == vals[1]:
            print(f"\n{YELLOW}两次读到的是同一个按钮 —— 可能是按错了同一个。{RESET}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identify", action="store_true",
                        help="引导式识别哪个物理按钮对应哪一位")
    args = parser.parse_args()
    enable_ansi()

    try:
        dev = TouchDevice().open()
    except (HDError, RuntimeError) as exc:
        print(f"无法打开设备:\n  {exc}\n", file=sys.stderr)
        print("先跑  python check_device.py  看是哪一步的问题。", file=sys.stderr)
        return 1

    try:
        if dev.seems_held_elsewhere():
            print(f"\n{YELLOW}设备正被另一个程序占用。{RESET}\n")
            print("读数会一直是占位值（关节角全 0）。请先关掉正在运行的")
            print("演示程序或诊断工具 —— 设备一次只能被一个程序占用。")
            return 2

        if args.identify:
            identify(dev)
        else:
            live(dev)
    finally:
        dev.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
