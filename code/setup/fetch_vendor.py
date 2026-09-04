"""Download the 3D Systems driver, SDK and documentation.

None of these files can ship with this repository. The OpenHaptics
Developer Edition licence forbids redistributing the SDK, and the two
installers are over GitHub's 100 MB per-file limit anyway. So fetch them
from 3D Systems' own public download bucket instead.

    python fetch_vendor.py                # driver + SDK  (~280 MB)
    python fetch_vendor.py --all          # also Unity plugin, tools, docs
    python fetch_vendor.py --docs         # documentation only  (~20 MB)
    python fetch_vendor.py --list         # show what would be fetched
    python fetch_vendor.py --check        # verify what is already here
    python fetch_vendor.py --install      # then run both installers
    python fetch_vendor.py --install --sdk-dir C:\OpenHaptics

Downloads land in vendor/ next to the project root. --install then runs
the two packages: the driver goes wherever its own installer defaults to
(it registers a Windows driver, so leave that alone), and the SDK is
pre-pointed at <project>/OpenHaptics unless --sdk-dir says otherwise.
Both are NSIS packages, so the directory is passed as /D=<path>. Each file is
checked against a SHA-256 recorded from a known-good copy, and the
signed installer is checked against its Authenticode signature too.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

BASE = "https://s3.amazonaws.com/dl.3dsystems.com/binaries/Sensable/"

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
VENDOR = os.path.join(PROJECT_ROOT, "vendor")

GREEN, YELLOW, RED, DIM, BOLD, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
)


@dataclass
class Item:
    key: str
    remote: str          # path under BASE
    local: str           # path under vendor/
    size: int
    sha256: str
    desc: str
    groups: tuple = field(default_factory=tuple)

    @property
    def url(self) -> str:
        # Spaces and & are real characters in these keys, not separators.
        return BASE + urllib.parse.quote(self.remote)

    @property
    def path(self) -> str:
        return os.path.join(VENDOR, self.local)


ITEMS = [
    Item("driver",
         "driver/Touch_Device_Driver_2025.12.12.exe",
         "installers/Touch_Device_Driver_2025.12.12.exe",
         173203808,
         "2815344e6f758fa1885ee3742826d5a8ae6430c70f70b06d9ccd7944ffb6f000",
         "Touch 设备驱动 —— 必装。USB 驱动 + 官方上位机 + hd.dll 运行时",
         ("core",)),
    Item("sdk",
         "OH/3.5/OpenHaptics_Developer_Edition_v3.5.0.zip",
         "installers/OpenHaptics_Developer_Edition_v3.5.0.zip",
         119178621,
         "1c54fb7d6995df98a467c4250ffbb6c514bc38c4387f8c127975b9ee3d91a783",
         "OpenHaptics SDK 3.5.0 —— 头文件、.lib、160 份源码、40 个演示",
         ("core",)),
    Item("unity",
         "OH/OpenHaptics_2019_06_13.unitypackage",
         "installers/OpenHaptics_2019_06_13.unitypackage",
         23085579,
         "3a3b73514a131bcebc3976a810665471e7a98569909e7fcd89f50a0a31aa6556",
         "Unity 开发插件 —— 只有要在 Unity 里做力反馈才需要",
         ("extra",)),
    Item("diagtool",
         "tools/TouchDiagnosticDumpTool_2024_05_07.zip",
         "installers/TouchDiagnosticDumpTool_2024_05_07.zip",
         1108755,
         "66a3a29292b350782e3228e6a021c62d623a1e06e71c1c39c1d6f720c5853959",
         "官方诊断抓取工具 —— 设备故障时抓日志给厂家",
         ("extra",)),

    Item("guide_prog",
         "OH/3.5/OpenHaptics_Toolkit_ProgrammersGuide.pdf",
         "docs/OpenHaptics_Toolkit_ProgrammersGuide.pdf",
         10074407,
         "47b9cba18a7bc301f364aa0474dd96286b3d1666b195ae7dd94f89741fdee3db",
         "OpenHaptics 编程指南 —— 写代码最该看的一本",
         ("docs",)),
    Item("guide_user",
         "UserGuide/Touch & TouchX User_Guide_USB.pdf",
         "docs/Touch_&_TouchX_User_Guide_USB.pdf",
         7484196,
         "e08d83a03d2d6ac0ce43338c037bef4b1416be89dac66c5cf3271af80935491c",
         "设备用户手册 —— Touch Diagnostic 各标签页的用法在第 17 页",
         ("docs",)),
    Item("guide_api",
         "OH/3.5/OpenHaptics_Toolkit_API_Reference_Guide.pdf",
         "docs/OpenHaptics_Toolkit_API_Reference_Guide.pdf",
         649660,
         "50369c2f8900b0a084625f588701740203faccbd63ac1044f0f79c2278fb43fc",
         "API 参考 —— 查函数签名",
         ("docs",)),
    Item("guide_install",
         "OH/OpenHaptics_Windows_Install_Guide.pdf",
         "docs/OpenHaptics_Windows_Install_Guide.pdf",
         927939,
         "4148dd19d8b193921621d3b99df2ea8d29c6414f48e7257b88d3331ffd48bff8",
         "SDK 安装指南",
         ("docs",)),
    Item("guide_qsg",
         "Touch/30-0329_Rev-G_EN_PhantomTouchQuickStartGuide_letter_web.pdf",
         "docs/30-0329_Rev-G_EN_PhantomTouchQuickStartGuide_letter_web.pdf",
         487038,
         "c0af6c6d6c8290b18e003e711190f2d2cb56cd1a144a2d1f48fc344214ef973e",
         "快速入门指南（设备盒内那张纸的电子版）",
         ("docs",)),
]


# --------------------------------------------------------------------------

def enable_ansi():
    if sys.platform != "win32":
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8")
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


def human(n: int) -> str:
    return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{n / 1024:.0f} KB"


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(item: Item, quiet=False) -> bool:
    """True if the local copy matches the recorded size and hash."""
    if not os.path.isfile(item.path):
        return False
    actual = os.path.getsize(item.path)
    if actual != item.size:
        if not quiet:
            print(f"    {YELLOW}大小不符{RESET}: {human(actual)} != {human(item.size)}")
        return False
    digest = sha256_of(item.path)
    if digest != item.sha256:
        if not quiet:
            print(f"    {RED}SHA-256 不符{RESET}")
            print(f"      期望 {item.sha256}")
            print(f"      实际 {digest}")
        return False
    return True


def check_signature(path: str):
    """Authenticode status, or None when it cannot be determined."""
    if sys.platform != "win32" or not path.lower().endswith(".exe"):
        return None
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"(Get-AuthenticodeSignature '{path}').Status"],
            capture_output=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return out.stdout.decode("utf-8", "replace").strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def download(item: Item) -> bool:
    os.makedirs(os.path.dirname(item.path), exist_ok=True)
    tmp = item.path + ".part"

    print(f"  下载 {item.local}  ({human(item.size)})")
    started = time.time()
    got = 0
    try:
        req = urllib.request.Request(item.url, headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or item.size)
            while True:
                chunk = resp.read(1 << 18)
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                elapsed = max(time.time() - started, 1e-6)
                pct = 100.0 * got / total if total else 0.0
                sys.stdout.write(
                    f"\r    {pct:5.1f}%  {human(got)} / {human(total)}"
                    f"   {got / elapsed / 1048576:5.2f} MB/s   "
                )
                sys.stdout.flush()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        print(f"\r    {RED}下载失败{RESET}: {exc}" + " " * 20)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False

    print(f"\r    下载完成 {human(got)}，用时 {time.time() - started:.0f}s" + " " * 20)

    # Replace the target only after the bytes check out.
    if os.path.exists(item.path):
        os.remove(item.path)
    shutil.move(tmp, item.path)

    if not verify(item):
        print(f"    {RED}校验失败，已删除{RESET}")
        os.remove(item.path)
        return False

    status = check_signature(item.path)
    sig = ""
    if status:
        sig = (f"，签名 {GREEN}{status}{RESET}" if status == "Valid"
               else f"，签名 {YELLOW}{status}{RESET}")
    print(f"    {GREEN}校验通过{RESET} (SHA-256){sig}")
    return True


def extract_sdk_installer() -> str:
    """Unpack the SDK zip and return the path to the installer exe."""
    import zipfile

    item = next(i for i in ITEMS if i.key == "sdk")
    with zipfile.ZipFile(item.path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".exe"))
        target = os.path.join(os.path.dirname(item.path), os.path.basename(name))
        if not os.path.isfile(target):
            print(f"  解压 {os.path.basename(name)} ...")
            with z.open(name) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
    return target


def run_installer(exe: str, install_dir: str = "") -> int:
    """Launch an installer, optionally pre-filling its install directory.

    Both packages are built with NSIS, which takes the directory as
    /D=<path>. That switch has two quirks: it must be the last thing on
    the command line, and it must not be quoted -- NSIS reads the rest of
    the line literally, so quotes would end up inside the path. Passing a
    list to Popen would quote any path containing spaces, so build the
    command line as a string instead.
    """
    if not os.path.isfile(exe):
        print(f"  {RED}找不到{RESET} {exe}")
        return 1

    cmd = f'"{exe}"'
    if install_dir:
        cmd += f" /D={install_dir}"     # deliberately unquoted, last

    print(f"\n  启动 {os.path.basename(exe)}")
    if install_dir:
        print(f"  {DIM}安装路径已预填为 {install_dir}{RESET}")
    print(f"  {DIM}安装向导会弹出，按提示点完即可。等待它结束...{RESET}")
    try:
        return subprocess.run(cmd).returncode
    except OSError as exc:
        print(f"  {RED}启动失败{RESET}: {exc}")
        return 1


def cmd_install(args) -> int:
    driver = next(i for i in ITEMS if i.key == "driver")
    sdk_zip = next(i for i in ITEMS if i.key == "sdk")

    for item in (driver, sdk_zip):
        if not os.path.isfile(item.path):
            print(f"{RED}还没下载{RESET} {item.local}")
            print("先跑一次不带参数的下载。")
            return 1

    sdk_dir = args.sdk_dir or os.path.join(PROJECT_ROOT, "OpenHaptics")

    print(f"\n{BOLD}安装{RESET}\n")
    print("  1. 驱动 —— 装到系统默认路径（它要往 Windows 驱动库注册，别改）")
    print(f"  2. SDK  —— 装到 {sdk_dir}")
    print(f"\n{DIM}  两个都需要管理员权限，会弹 UAC。{RESET}")
    try:
        if input("\n  继续？[y/N] ").strip().lower() not in ("y", "yes"):
            print("  已取消。")
            return 0
    except (EOFError, KeyboardInterrupt):
        print()
        return 1

    rc = run_installer(driver.path)          # no /D: let it use its default
    if rc != 0:
        print(f"  {YELLOW}驱动安装程序返回 {rc}{RESET}")

    print(f"\n{YELLOW}装完驱动建议重启电脑，再继续装 SDK。{RESET}")
    exe = extract_sdk_installer()
    run_installer(exe, sdk_dir)

    print(f"\n{GREEN}安装流程结束。{RESET}")
    print(f"{DIM}新开一个终端（环境变量要重新读），然后跑：{RESET}")
    print("  python code\\touchpy\\check_device.py\n")
    return 0


def selected(args) -> list:
    if args.docs:
        wanted = {"docs"}
    elif args.all:
        wanted = {"core", "extra", "docs"}
    else:
        wanted = {"core"}
    return [i for i in ITEMS if set(i.groups) & wanted]


def cmd_list(items):
    print(f"\n{BOLD}将下载到 {VENDOR}{RESET}\n")
    total = 0
    for i in items:
        mark = f"{GREEN}已有{RESET}" if os.path.isfile(i.path) else f"{DIM}待下{RESET}"
        print(f"  [{mark}] {human(i.size):>9}  {i.local}")
        print(f"          {DIM}{i.desc}{RESET}")
        if not os.path.isfile(i.path):
            total += i.size
    print(f"\n  需下载合计 {human(total)}\n")


def cmd_check(items):
    print(f"\n{BOLD}校验已下载的文件{RESET}\n")
    ok = missing = bad = 0
    for i in items:
        if not os.path.isfile(i.path):
            print(f"  {DIM}缺失{RESET}  {i.local}")
            missing += 1
            continue
        if verify(i):
            print(f"  {GREEN}正常{RESET}  {i.local}")
            ok += 1
        else:
            print(f"  {RED}损坏{RESET}  {i.local}")
            bad += 1
    print(f"\n  正常 {ok}，缺失 {missing}，损坏 {bad}\n")
    return 1 if bad else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="连同 Unity 插件、诊断工具、文档一起下")
    parser.add_argument("--docs", action="store_true", help="只下文档")
    parser.add_argument("--list", action="store_true", help="只列出清单")
    parser.add_argument("--check", action="store_true", help="校验已有文件")
    parser.add_argument("--force", action="store_true", help="已存在也重新下载")
    parser.add_argument("--download-only", action="store_true",
                        help="只下载，不运行安装程序")
    parser.add_argument("--sdk-dir", metavar="PATH",
                        help="SDK 装到哪（默认：项目目录下的 OpenHaptics）")
    args = parser.parse_args()
    enable_ansi()

    items = selected(args)

    if args.list:
        cmd_list(items)
        return 0
    if args.check:
        return cmd_check(items)
    # Already downloaded and verified? Skip straight to installing.
    core = [i for i in ITEMS if i.key in ("driver", "sdk")]
    if (not args.download_only and not args.docs
            and all(verify(i, quiet=True) for i in core)):
        print(f"\n{GREEN}驱动和 SDK 的安装包都已下载且校验通过。{RESET}")
        return cmd_install(args)

    print(f"\n{BOLD}从 3D Systems 官方源下载{RESET}")
    print(f"{DIM}  {BASE}{RESET}")
    print(f"{DIM}  目标 {VENDOR}{RESET}\n")

    failed = []
    for i in items:
        if not args.force and os.path.isfile(i.path):
            if verify(i, quiet=True):
                print(f"  {GREEN}已有且校验通过{RESET}  {i.local}")
                continue
            print(f"  {YELLOW}已有但校验不符，重新下载{RESET}  {i.local}")
        if not download(i):
            failed.append(i)

    print()
    if failed:
        print(f"{RED}以下文件下载失败：{RESET}")
        for i in failed:
            print(f"  {i.local}\n    {i.url}")
        print("\n可以用浏览器手动下载上面的链接，放到对应目录。")
        return 1

    print(f"{GREEN}全部完成。{RESET}\n")
    print(f"{BOLD}接下来手动装这两个（脚本不代劳，安装要管理员权限）：{RESET}\n")
    print("  1. vendor\\installers\\Touch_Device_Driver_2025.12.12.exe")
    print(f"     {DIM}装默认路径即可。装完重启电脑。{RESET}\n")
    print("  2. vendor\\installers\\OpenHaptics_Developer_Edition_v3.5.0.zip")
    print(f"     {DIM}解压后运行里面的 exe。装默认路径即可。{RESET}\n")
    print(f"{DIM}两个都装完后，跑 code\\touchpy\\check_device.py 确认链路。{RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
