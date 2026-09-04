"""Text-menu launcher for the Touch programs.

The graphical version is touch_launcher.pyw; this is the same catalogue
driven from a terminal. Both read catalog.py, so the list of programs and
the launch rules exist in one place only.

    python launch.py          # menu
    python launch.py 8        # run entry 8 straight away
    python launch.py --list   # print the catalogue and exit
"""

from __future__ import annotations

import os
import sys

# Works whether launched from this directory or by full path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog  # noqa: E402

BOLD, DIM, GREEN, YELLOW, RED, RESET = (
    "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"
)


def enable_ansi():
    if sys.platform != "win32":
        return
    # This menu is in Chinese; a console left on the legacy code page renders
    # it as mojibake. Force UTF-8 and turn on VT escape processing.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetConsoleOutputCP(65001)
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, mode.value | 0x4)
    except Exception:
        pass


def print_menu():
    print(f"\n{BOLD}3D Systems Touch — 可视化程序{RESET}")
    print(f"{DIM}驱动目录: {catalog.ROOT}{RESET}\n")
    n = 0
    for category, apps in catalog.CATALOGUE:
        print(f"{BOLD}{category}{RESET}")
        for app in apps:
            n += 1
            if not app.exists:
                mark = f"  {RED}[缺失]{RESET}"
            elif app.console:
                mark = f"  {DIM}[无图形]{RESET}"
            else:
                mark = ""
            star = f"{YELLOW}★{RESET} " if app.pick else "  "
            print(f"  {GREEN}{n:2d}{RESET}  {star}{app.name}{mark}")
            print(f"       {DIM}{app.desc.splitlines()[0]}{RESET}")
        print()
    print(f"   {DIM}q  退出{RESET}\n")


def launch(app: catalog.App) -> int:
    if not app.exists:
        print(f"{RED}找不到:{RESET} {app.exe}")
        return 1

    print(f"\n{GREEN}启动{RESET} {app.name}")
    print(f"{DIM}  {app.exe}{RESET}")
    print(f"{DIM}  工作目录 {app.workdir}{RESET}")
    print(f"{DIM}  关闭该窗口后返回菜单...{RESET}\n")

    try:
        proc = catalog.spawn(app)
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print(f"\n{YELLOW}已中断{RESET}")
        return 1
    except OSError as exc:
        print(f"{RED}启动失败:{RESET} {exc}")
        return 1

    if proc.returncode != 0:
        print(f"{YELLOW}退出码 {proc.returncode}{RESET} "
              f"{DIM}(演示程序用 Esc/关窗退出时经常非零，通常不是问题){RESET}")
    else:
        print(f"{GREEN}正常退出{RESET}")
    return 0


def main():
    enable_ansi()
    items = catalog.flatten()

    if "--list" in sys.argv:
        print_menu()
        missing = [a for _c, a in items if not a.exists]
        print(f"{len(items) - len(missing)}/{len(items)} 个程序可用")
        return 0

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        try:
            index = int(args[0])
            if not 1 <= index <= len(items):
                raise ValueError
        except ValueError:
            print(f"编号要在 1..{len(items)} 之间")
            return 2
        return launch(items[index - 1][1])

    while True:
        print_menu()
        try:
            choice = input("选一个编号 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice.lower() in ("q", "quit", "exit", ""):
            return 0
        try:
            index = int(choice)
            if not 1 <= index <= len(items):
                raise ValueError
        except ValueError:
            print(f"{RED}请输入 1..{len(items)} 之间的编号，或 q 退出{RESET}")
            continue
        launch(items[index - 1][1])
        input(f"\n{DIM}回车返回菜单...{RESET}")


if __name__ == "__main__":
    sys.exit(main())
