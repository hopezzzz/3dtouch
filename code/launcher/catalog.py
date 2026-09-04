"""The catalogue of Touch programs, plus what it takes to actually start them.

Shared by the GUI launcher and the text menu, so the list of programs and
the launch rules live in exactly one place.

Three things stop most of these programs from running if you just
double-click the exe, and `build_env` / `App.workdir` handle all three:

  * The QuickHaptics demos and the HL examples ship without their DLLs.
    hd.dll, hl.dll and glut32.dll live in the driver's root directory, so
    that has to be on PATH or the program dies on startup.

  * QH.dll (QuickHaptics) reads
    $(OH_SDK_BASE)/QuickHaptics/Repository/... for its fonts and error
    textures, and refuses to start without OH_SDK_BASE. The SDK installer
    does set it, machine-wide -- but a process only reads the environment
    from the registry when it starts, so any shell opened before the SDK
    was installed passes a stale environment to its children. setdefault
    below keeps an inherited value and supplies one otherwise.
    HL_DOP_Demo needs it too, for its spine model.

  * The demos load models by relative path, so each has to start from its
    own bin directory.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Where things are installed
# --------------------------------------------------------------------------

# Set TOUCH_DRIVER_ROOT to override; otherwise try the standard install
# locations first, then a couple of places people commonly relocate to.
DRIVER_ROOT = os.environ.get("TOUCH_DRIVER_ROOT", "")
FALLBACK_ROOTS = [
    r"C:\Program Files\3D Systems\Phantom Device Drivers",
    r"C:\Program Files\3D Systems\Touch Device Driver",
    r"C:\Program Files\SensAble\Phantom Device Drivers",
    r"C:\Program Files (x86)\3D Systems\Phantom Device Drivers",
    r"D:\Tool_Software\Phantom Device Drivers",
]


def driver_root() -> str:
    for root in ([DRIVER_ROOT] if DRIVER_ROOT else []) + FALLBACK_ROOTS:
        if os.path.isfile(os.path.join(root, "hd.dll")):
            return root
    return DRIVER_ROOT or FALLBACK_ROOTS[0]


ROOT = driver_root()

# The driver and the SDK are separate installs and need not sit near each
# other. The SDK installer records its location in OH_SDK_BASE, so trust
# that first; the fallbacks cover a shell whose environment predates the
# install, and the SDK's own default install path.
_PROJECT_ROOT = os.path.abspath(
    # this file -> launcher/ -> code/ -> project root
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)

_SDK_FALLBACKS = [
    # This project keeps the SDK next to its code, not under it.
    os.path.join(_PROJECT_ROOT, "OpenHaptics"),
    os.path.join(ROOT, "OpenHaptics"),
    r"C:\OpenHaptics\Developer\3.5.0",
    r"C:\Program Files\3D Systems\OpenHaptics\Developer\3.5.0",
]


def sdk_base() -> str:
    candidates = []
    if os.environ.get("OH_SDK_BASE"):
        candidates.append(os.environ["OH_SDK_BASE"])
    candidates += _SDK_FALLBACKS
    for base in candidates:
        if os.path.isfile(os.path.join(base, "include", "HD", "hd.h")):
            return base
    return candidates[0] if candidates else ""


OH_BASE = sdk_base()
QH = os.path.join(OH_BASE, "Quickhaptics", "bin", "x64")
EX = os.path.join(OH_BASE, "examples", "bin", "x64")


# --------------------------------------------------------------------------
# Entries
# --------------------------------------------------------------------------

@dataclass
class App:
    name: str
    exe: str
    desc: str
    cwd: str = ""
    console: bool = False   # no 3D window; force feedback and text only
    pick: bool = False      # worth trying first

    @property
    def workdir(self) -> str:
        return self.cwd or os.path.dirname(self.exe)

    @property
    def exists(self) -> bool:
        return os.path.isfile(self.exe)


CATALOGUE = [
    ("官方上位机 / 诊断工具", [
        App("Touch Diagnostic", os.path.join(ROOT, "Touch_Diagnostic_LegacyVersion.exe"),
            "诊断台：校准、编码器量程、Box Test 力反馈测试、伺服环统计。\n"
            "五个标签页从左到右走一遍，右下角箭头是下一步。\n"
            "Box Test 是重点 —— 那里能第一次真正感受到力反馈。", pick=True),
        App("Touch Smart Setup", os.path.join(ROOT, "Touch_SmartSetup.exe"),
            "说明书第 4-6 步的那个向导：\n"
            "校准（笔插进墨盒）→ 球体模拟测试 → 空心立方体测试 → 保存配置。"),
        App("Touch Setup", os.path.join(ROOT, "Touch_Setup.exe"),
            "设备配置：选择设备、命名、保存配置。\n"
            "已经用 Smart Setup 配过就不需要这个。"),
        App("Phantom Diagnostic", os.path.join(ROOT, "Phantom_Diagnostic.exe"),
            "Phantom 系列通用诊断工具。"),
        App("Advanced HID Touch Config", os.path.join(ROOT, "AdvancedHIDTouchConfig.exe"),
            "HID 固件版设备的高级配置（VID_2988&PID_0304 就是 HID 版）。"),
    ]),
    ("力反馈演示", [
        App("Touch Demo", os.path.join(ROOT, "TouchDemo.exe"),
            "官方入门演示。"),
        App("Haptic Demo (Unity)",
            os.path.join(ROOT, "OpenHaptics_Demos", "HapticDemo", "HapticDemo.exe"),
            "Unity 引擎做的力反馈场景。\n"
            "用的就是 OpenHaptics 的 Unity 插件（unitypackage 在 vendor/installers 里）。"),
    ]),
    ("QuickHaptics 3D 演示", [
        App("牙科探针查龋齿", os.path.join(QH, "TeethCavityPickGLUT.exe"),
            "拿探针在牙模上找龋洞。\n"
            "探针掉进龋洞的手感和滑过硬牙釉质完全不同 —— 牙医培训靠的就是这个。",
            QH, pick=True),
        App("骷髅 + 库仑力场", os.path.join(QH, "SkullCoulombForceGLUT.exe"),
            "3D 骷髅模型，笔尖靠近时能感受到库仑力场的吸引/排斥。", QH),
        App("软绵绵的牛", os.path.join(QH, "SpongyCowGLUT.exe"),
            "摸一头有弹性的牛，体会柔性材质的手感。", QH),
        App("摘苹果", os.path.join(QH, "pickApplesGLUT.exe"),
            "从篮子里把苹果一个个抓起来。", QH),
        App("转地球", os.path.join(QH, "EarthSpinGLUT.exe"),
            "用笔拨动地球仪。", QH),
        App("复杂场景", os.path.join(QH, "ComplexSceneGLUT.exe"),
            "多物体多材质混合场景。", QH),
        App("形状深度反馈", os.path.join(QH, "ShapeDepthFeedback.exe"),
            "兔子模型 + 铅笔，按压越深反馈力越大。", QH),
        App("最简球体", os.path.join(QH, "SimpleSphereGLUT.exe"),
            "QuickHaptics 最小示例：一个能摸的球。", QH),
        App("多窗口", os.path.join(QH, "MultipleWindowsWin32.exe"),
            "同一个触觉场景渲染到多个窗口。", QH),
    ]),
    ("HL 高层 API 示例（图形）", [
        App("材质手感对比", os.path.join(EX, "HL", "HapticMaterials.exe"),
            "硬 / 软 / 粘 / 滑几种材质并排，一个个摸过去。\n"
            "能直接体会 stiffness、damping、friction 这几个参数对应什么手感 ——\n"
            "以后自己写代码调参，调的就是这几个数。", pick=True),
        App("脊椎触觉位移贴图", os.path.join(EX, "HL", "HL_DOP_Demo.exe"),
            "腰椎模型 + 球形探针，用位移贴图做表面细节。\n"
            "需要 OH_SDK_BASE 才能找到模型和纹理（启动器已自动设置）。", pick=True),
        App("运动约束", os.path.join(EX, "HL", "Constraints.exe"),
            "把笔尖约束在点 / 线 / 面上。\n"
            "手术导航机器人的核心技术：医生只能沿规划路径走，越界就被挡住。",
            pick=True),
        App("Haptic Viewer", os.path.join(EX, "HL", "HapticViewer.exe"),
            "模型浏览器，可加载 OpenHaptics/examples/models 里的\n"
            "Demon / Head / Teapot / Torus / TorusKnot / WavySurface 等模型来摸。"),
        App("可变形表面", os.path.join(EX, "HL", "SimpleDeformableSurface.exe"),
            "按下去会真的凹陷的弹性网面，软组织仿真的基础。", pick=True),
        App("刚体动力学", os.path.join(EX, "HL", "SimpleRigidBodyDynamics.exe"),
            "用笔推动带物理的刚体。"),
        App("形状操控", os.path.join(EX, "HL", "ShapeManipulation.exe"),
            "抓取并移动 3D 物体。"),
        App("点操控", os.path.join(EX, "HL", "PointManipulation.exe"),
            "抓取控制点来变形物体。"),
        App("捏取演示", os.path.join(EX, "HL", "SimplePinchDemo.exe"),
            "双指捏取交互。"),
        App("触觉事件", os.path.join(EX, "HL", "Events.exe"),
            "接触 / 离开 / 按钮等事件的回调演示。"),
        App("Hello Sphere", os.path.join(EX, "HL", "HelloSphere.exe"),
            "HL API 入门：一个能摸的球。"),
        App("Hello Haptics", os.path.join(EX, "HL", "HelloHaptics.exe"),
            "HL API 最小示例。"),
    ]),
    ("HD 底层 API 示例（图形）", [
        App("库仑力场", os.path.join(EX, "HD", "CoulombField.exe"),
            "点电荷力场可视化。"),
        App("粒子华尔兹", os.path.join(EX, "HD", "ParticleWaltz.exe"),
            "弹簧连接的粒子系统。"),
        App("简单触觉场景", os.path.join(EX, "HD", "SimpleHapticScene.exe"),
            "用 HD 底层 API 手写的基础场景。"),
        App("滑动接触", os.path.join(EX, "HD", "SlidingContact.exe"),
            "沿表面滑动的摩擦力模型。"),
        App("点吸附", os.path.join(EX, "HD", "PointSnapping.exe"),
            "笔尖被吸附到特征点上。"),
        App("点操控 (HD)", os.path.join(EX, "HD", "PointManipulation.exe"),
            "HD 层的点操控。"),
    ]),
    ("纯手感（无图形，闭眼感受）", [
        App("振动效果", os.path.join(EX, "HD", "Vibration.exe"),
            "笔杆会真的振起来。没有画面，闭上眼睛感受。", console=True, pick=True),
        App("锚定弹簧力", os.path.join(EX, "HD", "AnchoredSpringForce.exe"),
            "一根看不见的弹簧把笔尖拉回锚点。", console=True),
        App("无摩擦平面", os.path.join(EX, "HD", "FrictionlessPlane.exe"),
            "一面看不见但摸得到的墙。\n"
            "code/touchpy/demo_force.py 干的是同一件事。", console=True),
        App("无摩擦球体", os.path.join(EX, "HD", "FrictionlessSphere.exe"),
            "一个看不见但摸得到的球。", console=True),
        App("关节力矩控制", os.path.join(EX, "HD", "CommandJointTorque.exe"),
            "直接给三个关节电机下力矩指令。", console=True),
    ]),
    ("诊断 / 学习用（控制台）", [
        App("查询设备", os.path.join(EX, "HD", "QueryDevice.exe"),
            "打印设备全部属性和实时状态。", console=True),
        App("伺服环速率", os.path.join(EX, "HD", "ServoLoopRate.exe"),
            "测量伺服环实际速率，应该在 1000 Hz 附近。", console=True),
        App("伺服环占空比", os.path.join(EX, "HD", "ServoLoopDutyCycle.exe"),
            "测量伺服环负载。", console=True),
        App("Hello Haptic Device", os.path.join(EX, "HD", "HelloHapticDevice.exe"),
            "HD API 最小示例：读位置、输出力。", console=True),
        App("校准", os.path.join(EX, "HD", "Calibration.exe"),
            "官方校准示例。code/touchpy/calibrate.py 就是照它写的。", console=True),
        App("错误处理", os.path.join(EX, "HD", "ErrorHandling.exe"),
            "HD API 错误处理示例。", console=True),
        App("防止电机过热", os.path.join(EX, "HD", "PreventWarmMotors.exe"),
            "长时间输出力时的电机温度管理。", console=True),
    ]),
]


def flatten():
    """[(category, App), ...] in menu order."""
    return [(cat, app) for cat, apps in CATALOGUE for app in apps]


# --------------------------------------------------------------------------
# Launching
# --------------------------------------------------------------------------

def build_env() -> dict:
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([
        ROOT,                                   # hd.dll, hl.dll, glut32.dll
        os.path.join(EX, "HD"),                 # a second copy of those
        # QH.dll and QHGLUTWrapper.dll, which the QuickHaptics demos import
        # directly. The SDK installer also drops them into System32, so on
        # the machine that ran the installer the demos start either way --
        # but a copied-not-installed SDK tree has them only here.
        os.path.join(OH_BASE, "Quickhaptics", "lib", "x64", "Release"),
        env.get("PATH", ""),
    ])
    env.setdefault("OH_SDK_BASE", OH_BASE)
    return env


def spawn(app: App) -> subprocess.Popen:
    """Start one program. Raises OSError if it cannot be started."""
    if not app.exists:
        raise FileNotFoundError(app.exe)

    flags = 0
    if sys.platform == "win32" and app.console:
        # Console demos print instructions and read keys; without a console
        # of their own they are invisible when started from a GUI.
        flags = subprocess.CREATE_NEW_CONSOLE

    return subprocess.Popen(
        [app.exe], cwd=app.workdir, env=build_env(), creationflags=flags
    )


# --------------------------------------------------------------------------
# Is the device plugged in?
# --------------------------------------------------------------------------

VENDOR_ID = "2988"
PRODUCT_NAMES = {
    "0301": "Touch (USB, CDC)",
    "0302": "Geomagic Touch (USB, CDC)",
    "0303": "Touch X (USB, CDC)",
    "0304": "Touch (USB, HID)",
}


def device_status():
    """(online: bool, description: str). Shells out, so call off the UI thread."""
    if sys.platform != "win32":
        return False, "仅支持 Windows"
    script = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
        "Get-PnpDevice -PresentOnly | "
        f"Where-Object {{ $_.InstanceId -match 'VID_{VENDOR_ID}' }} | "
        "ForEach-Object { $_.InstanceId }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        text = out.stdout.decode("utf-8", "replace")
    except (subprocess.SubprocessError, OSError) as exc:
        return False, f"查询失败: {exc}"

    ids = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not ids:
        return False, "设备未连接"
    for pid, label in PRODUCT_NAMES.items():
        if any(f"PID_{pid}" in i.upper() for i in ids):
            return True, label
    return True, "已连接（型号未识别）"
