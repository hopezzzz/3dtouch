"""ctypes binding for the OpenHaptics HD API (3D Systems Touch).

The HD API drives the device from a real-time servo loop that ticks at
1 kHz in its own thread.  Application code never touches that thread
directly; it hands the scheduler a callback and the scheduler runs it
between servo ticks.

Two ways to get at device state, and the difference matters:

  * ``TouchDevice.read()`` uses ``hdScheduleSynchronous``.  The callback
    runs once, in the servo thread, and the caller blocks until it
    returns.  Python holds the GIL for the few microseconds it takes to
    copy six doubles, then gives it back.  Poll this as fast as you like
    up to a few hundred Hz -- the servo loop never notices.

  * ``TouchDevice.enable_force_output()`` installs an *asynchronous*
    callback, which the scheduler then calls on every one of its 1000
    ticks per second.  A Python callback there means acquiring the GIL
    1000 times a second from a real-time thread.  It works, but the
    callback must stay allocation-free, and a busy main thread will show
    up as a dip in HD_INSTANTANEOUS_UPDATE_RATE.  Reading does not need
    this; only force output does.

Units follow the HD API: position in millimetres, angles in radians,
force in newtons.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_char_p,
    c_double,
    c_int,
    c_uint,
    c_ushort,
    c_void_p,
)
from dataclasses import dataclass, field
from typing import Optional, Sequence

import hd_constants as C

# --------------------------------------------------------------------------
# Locating hd.dll
# --------------------------------------------------------------------------

# The Touch device driver ships hd.dll; the OpenHaptics SDK ships a copy too.
# Neither installer reliably puts it on PATH, so look in the usual places.
_DLL_SEARCH_DIRS = [
    r"C:\Program Files\3D Systems\Phantom Device Drivers",
    r"C:\Program Files\3D Systems\Touch Device Driver",
    r"C:\Program Files (x86)\3D Systems\Phantom Device Drivers",
    r"C:\Program Files\SensAble\Phantom Device Drivers",
    r"C:\Program Files\3D Systems\OpenHaptics\Developer\3.5.0\lib\x64\Release",
    r"C:\OpenHaptics\Developer\3.5.0\lib\x64\Release",
    r"C:\Windows\System32",
    # A relocated install this project has been used with.
    r"D:\Tool_Software\Phantom Device Drivers",
]


def _candidate_dirs():
    env = os.environ.get("TOUCH_HD_DIR")
    if env:
        yield env
    yield from _DLL_SEARCH_DIRS
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry:
            yield entry


def _load_hd_library():
    if sys.platform != "win32":
        return ctypes.CDLL("libHD.so")

    if ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError(
            "This is 32-bit Python, but the installed hd.dll is x64. "
            "Use a 64-bit Python interpreter."
        )

    tried = []
    for directory in _candidate_dirs():
        dll = os.path.join(directory, "hd.dll")
        if not os.path.isfile(dll):
            continue
        tried.append(dll)
        # hd.dll pulls in siblings (Qt, PhantomIOLib, ...) from its own
        # directory, which Windows will not search unless we say so.
        try:
            os.add_dll_directory(directory)
        except (AttributeError, OSError):
            pass
        try:
            return ctypes.WinDLL(dll)
        except OSError as exc:
            tried[-1] += f"  ({exc})"
            continue

    detail = "\n  ".join(tried) if tried else "(no hd.dll found in any search path)"
    raise RuntimeError(
        "Could not load hd.dll.\n"
        "  Install the Touch Device Driver, or set TOUCH_HD_DIR to the folder "
        "containing hd.dll.\n"
        f"  Tried:\n  {detail}"
    )


_hd = _load_hd_library()


# --------------------------------------------------------------------------
# Types and prototypes
# --------------------------------------------------------------------------

HHD = c_uint
HD_INVALID_HANDLE = 0xFFFFFFFF

# HDCALLBACK is __stdcall; on x64 that collapses to the single Windows ABI,
# but WINFUNCTYPE keeps the declaration honest on 32-bit too.
if sys.platform == "win32":
    HDSchedulerCallback = ctypes.WINFUNCTYPE(c_uint, c_void_p)
else:
    HDSchedulerCallback = ctypes.CFUNCTYPE(c_uint, c_void_p)


class HDErrorInfo(Structure):
    _fields_ = [
        ("errorCode", c_uint),
        ("internalErrorCode", c_int),
        ("hHD", HHD),
    ]


_hd.hdInitDevice.argtypes = [c_char_p]
_hd.hdInitDevice.restype = HHD
_hd.hdDisableDevice.argtypes = [HHD]
_hd.hdDisableDevice.restype = None
_hd.hdMakeCurrentDevice.argtypes = [HHD]
_hd.hdMakeCurrentDevice.restype = None
_hd.hdBeginFrame.argtypes = [HHD]
_hd.hdBeginFrame.restype = None
_hd.hdEndFrame.argtypes = [HHD]
_hd.hdEndFrame.restype = None

_hd.hdGetError.argtypes = []
_hd.hdGetError.restype = HDErrorInfo
_hd.hdGetErrorString.argtypes = [c_uint]
_hd.hdGetErrorString.restype = c_char_p

_hd.hdEnable.argtypes = [c_uint]
_hd.hdEnable.restype = None
_hd.hdDisable.argtypes = [c_uint]
_hd.hdDisable.restype = None

_hd.hdGetIntegerv.argtypes = [c_uint, POINTER(c_int)]
_hd.hdGetIntegerv.restype = None
_hd.hdGetDoublev.argtypes = [c_uint, POINTER(c_double)]
_hd.hdGetDoublev.restype = None
_hd.hdSetDoublev.argtypes = [c_uint, POINTER(c_double)]
_hd.hdSetDoublev.restype = None
_hd.hdGetString.argtypes = [c_uint]
_hd.hdGetString.restype = c_char_p

_hd.hdStartScheduler.argtypes = []
_hd.hdStartScheduler.restype = None
_hd.hdStopScheduler.argtypes = []
_hd.hdStopScheduler.restype = None
_hd.hdScheduleSynchronous.argtypes = [HDSchedulerCallback, c_void_p, c_ushort]
_hd.hdScheduleSynchronous.restype = None
_hd.hdScheduleAsynchronous.argtypes = [HDSchedulerCallback, c_void_p, c_ushort]
_hd.hdScheduleAsynchronous.restype = ctypes.c_ulong
_hd.hdUnschedule.argtypes = [ctypes.c_ulong]
_hd.hdUnschedule.restype = None

_hd.hdCheckCalibration.argtypes = []
_hd.hdCheckCalibration.restype = c_uint
_hd.hdCheckCalibrationStyle.argtypes = []
_hd.hdCheckCalibrationStyle.restype = c_uint
_hd.hdUpdateCalibration.argtypes = [c_uint]
_hd.hdUpdateCalibration.restype = None

HD_DEFAULT_SCHEDULER_PRIORITY = 20000  # midpoint of the 0..65535 range


# Failures that, in practice, almost always mean another program already
# has the device: a demo or the Touch Diagnostic left open in another
# window. The API's own wording ("timer", "invalid value") gives no hint
# of that, so say it plainly.
_BUSY_CODES = {
    0x0304,   # HD_TIMER_ERROR - cannot start or maintain the servo loop
    0x0101,   # HD_INVALID_VALUE from hdInitDevice on an already-open device
}
_BUSY_HINT = (
    "\n  提示：设备可能已被另一个程序占用（演示程序、Touch Diagnostic 等）。"
    "\n  设备一次只能被一个程序打开，请先关掉它再重试。"
)


class HDError(RuntimeError):
    """An error popped off the HD API's error stack."""

    def __init__(self, message, info: HDErrorInfo):
        self.error_code = info.errorCode
        self.internal_error_code = info.internalErrorCode
        text = _hd.hdGetErrorString(info.errorCode)
        self.description = text.decode("utf-8", "replace") if text else "unknown error"
        hint = _BUSY_HINT if self.error_code in _BUSY_CODES else ""
        super().__init__(
            f"{message}: {self.description} "
            f"(errorCode=0x{self.error_code:04x}, internal={self.internal_error_code})"
            f"{hint}"
        )


def _check(context: str):
    """Raise if the HD API pushed an error, otherwise drain the stack."""
    info = _hd.hdGetError()
    if info.errorCode != C.HD_SUCCESS:
        # Drain the rest so a later call does not report this same error.
        while _hd.hdGetError().errorCode != C.HD_SUCCESS:
            pass
        raise HDError(context, info)


# --------------------------------------------------------------------------
# Device state
# --------------------------------------------------------------------------

BUTTON_MASKS = {
    1: C.HD_DEVICE_BUTTON_1,
    2: C.HD_DEVICE_BUTTON_2,
    3: C.HD_DEVICE_BUTTON_3,
    4: C.HD_DEVICE_BUTTON_4,
}


@dataclass
class TouchState:
    """One snapshot of the device, taken inside a single servo frame."""

    position: tuple = (0.0, 0.0, 0.0)          # mm, stylus tip
    velocity: tuple = (0.0, 0.0, 0.0)          # mm/s
    transform: tuple = ()                       # 4x4 column-major, 16 doubles
    joint_angles: tuple = (0.0, 0.0, 0.0)      # rad, the three arm joints
    gimbal_angles: tuple = (0.0, 0.0, 0.0)     # rad, the three stylus joints
    force: tuple = (0.0, 0.0, 0.0)             # N, force currently commanded
    buttons: int = 0                            # bitmask
    update_rate: float = 0.0                    # Hz, servo loop's own estimate

    def button(self, n: int) -> bool:
        """True if stylus button ``n`` (1-based) is down."""
        return bool(self.buttons & BUTTON_MASKS[n])

    @property
    def buttons_down(self):
        return tuple(n for n, mask in BUTTON_MASKS.items() if self.buttons & mask)

    @property
    def orientation(self):
        """Rotation part of the transform as three row tuples."""
        t = self.transform
        if len(t) != 16:
            return ()
        # Column-major: element (row, col) lives at t[col * 4 + row].
        return tuple(tuple(t[col * 4 + row] for col in range(3)) for row in range(3))


# --------------------------------------------------------------------------
# Device
# --------------------------------------------------------------------------

class TouchDevice:
    """A single Touch device.

    Usage::

        with TouchDevice() as dev:
            state = dev.read()
            print(state.position, state.buttons_down)
    """

    def __init__(self, config_name: Optional[str] = None):
        # HD_DEFAULT_DEVICE is NULL, which picks the device named "Default
        # Device" in the driver's configuration -- what Touch Smart Setup
        # writes when you save a configuration.
        self.config_name = config_name
        self.handle = HD_INVALID_HANDLE
        self._scheduler_running = False
        self._force_handle = None

        # Buffers reused by the servo callbacks. Allocating inside a
        # callback that runs 1000 times a second is how you get audible
        # buzzing, so everything is allocated once here.
        self._buf3 = (c_double * 3)()
        self._buf16 = (c_double * 16)()
        self._buf1 = (c_double * 1)()
        self._bufi = (c_int * 1)()
        self._commanded_force = (c_double * 3)()

        self._state = TouchState()
        self._calib_status = 0
        self._calib_style = 0
        self._snapshot_cb = HDSchedulerCallback(self._snapshot)
        self._force_cb = HDSchedulerCallback(self._force_tick)
        self._calib_status_cb = HDSchedulerCallback(self._calibration_status_tick)
        self._calib_update_cb = HDSchedulerCallback(self._calibration_update_tick)
        self._ready_cb = HDSchedulerCallback(self._ready_tick)

    # -- lifecycle ---------------------------------------------------------

    def open(self) -> "TouchDevice":
        name = self.config_name.encode("utf-8") if self.config_name else None
        self.handle = _hd.hdInitDevice(name)
        _check("hdInitDevice failed")
        if self.handle == HD_INVALID_HANDLE:
            raise HDError(
                "hdInitDevice returned an invalid handle",
                HDErrorInfo(C.HD_SUCCESS, 0, HD_INVALID_HANDLE),
            )

        _hd.hdStartScheduler()
        _check("hdStartScheduler failed")
        self._scheduler_running = True
        self._wait_until_ready()
        return self

    def _ready_tick(self, _user_data):
        h = self.handle
        _hd.hdBeginFrame(h)
        _hd.hdGetDoublev(C.HD_INSTANTANEOUS_UPDATE_RATE, self._buf1)
        _hd.hdEndFrame(h)
        return C.HD_CALLBACK_DONE

    def _wait_until_ready(self, timeout: float = 3.0):
        """Block until the servo loop is actually running.

        hdStartScheduler returns before the servo thread has completed its
        first frame. Opening a frame in that window fails with "hdEndFrame
        ... without a matching hdBeginFrame", and the first sample that
        does get through carries uninitialised state rather than a real
        reading. So poll a throwaway frame until one comes back clean.
        """
        deadline = time.perf_counter() + timeout
        last_error = None
        clean_in_a_row = 0
        # One good frame is not enough: on a cold start the first frame can
        # come back clean and the next still trip HD_ILLEGAL_END.
        needed = 3

        while time.perf_counter() < deadline:
            self._buf1[0] = 0.0
            _hd.hdScheduleSynchronous(
                self._ready_cb, None, HD_DEFAULT_SCHEDULER_PRIORITY
            )
            info = _hd.hdGetError()
            if info.errorCode == C.HD_SUCCESS and self._buf1[0] > 0.0:
                clean_in_a_row += 1
                if clean_in_a_row >= needed:
                    # Drain anything the servo thread pushed while we were
                    # looping, so the caller's first read starts clean.
                    while _hd.hdGetError().errorCode != C.HD_SUCCESS:
                        pass
                    return
            else:
                clean_in_a_row = 0
                last_error = info
                while _hd.hdGetError().errorCode != C.HD_SUCCESS:
                    pass
            time.sleep(0.005)

        self.close()
        raise HDError(
            f"the servo loop did not start within {timeout:.0f}s",
            last_error or HDErrorInfo(C.HD_SUCCESS, 0, self.handle),
        )

    def close(self):
        if self._force_handle is not None:
            _hd.hdUnschedule(self._force_handle)
            self._force_handle = None
        if self._scheduler_running:
            _hd.hdStopScheduler()
            self._scheduler_running = False
        if self.handle != HD_INVALID_HANDLE:
            _hd.hdDisableDevice(self.handle)
            self.handle = HD_INVALID_HANDLE

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()
        return False

    # -- identity ----------------------------------------------------------

    def _string(self, pname):
        raw = _hd.hdGetString(pname)
        return raw.decode("utf-8", "replace") if raw else ""

    @property
    def model(self) -> str:
        return self._string(C.HD_DEVICE_MODEL_TYPE)

    @property
    def vendor(self) -> str:
        return self._string(C.HD_DEVICE_VENDOR)

    @property
    def serial_number(self) -> str:
        return self._string(C.HD_DEVICE_SERIAL_NUMBER)

    @property
    def driver_version(self) -> str:
        return self._string(C.HD_VERSION)

    def info(self) -> dict:
        """Static device properties. Safe to call from the main thread."""
        _hd.hdGetDoublev(C.HD_NOMINAL_MAX_FORCE, self._buf1)
        max_force = self._buf1[0]
        usable = (c_double * 6)()
        _hd.hdGetDoublev(C.HD_USABLE_WORKSPACE_DIMENSIONS, usable)
        _check("reading device info failed")
        return {
            "model": self.model,
            "vendor": self.vendor,
            "serial_number": self.serial_number,
            "driver_version": self.driver_version,
            "nominal_max_force_N": max_force,
            # min x,y,z then max x,y,z, in mm
            "usable_workspace_mm": tuple(usable),
        }

    # -- calibration -------------------------------------------------------

    # Both calibration calls have to happen in the servo thread -- the
    # SDK's own Calibration.c example wraps each one in a scheduler
    # callback. Calling them from the application thread appears to work
    # (no error is raised) but the status never advances past
    # NEEDS_UPDATE, because the servo loop is the only thing that can
    # actually commit the change.

    CALIBRATION_STYLES = (
        # Highest preference first, matching the SDK example: auto beats
        # inkwell, inkwell beats a manual encoder reset.
        (C.HD_CALIBRATION_AUTO, "auto"),
        (C.HD_CALIBRATION_INKWELL, "inkwell"),
        (C.HD_CALIBRATION_ENCODER_RESET, "encoder_reset"),
    )

    def _calibration_status_tick(self, _user_data):
        h = self.handle
        _hd.hdBeginFrame(h)
        self._calib_status = _hd.hdCheckCalibration()
        _hd.hdEndFrame(h)
        return C.HD_CALLBACK_DONE

    def _calibration_update_tick(self, _user_data):
        if _hd.hdCheckCalibration() == C.HD_CALIBRATION_NEEDS_UPDATE:
            _hd.hdUpdateCalibration(self._calib_style)
        return C.HD_CALLBACK_DONE

    def calibration_status(self) -> str:
        _hd.hdScheduleSynchronous(
            self._calib_status_cb, None, HD_DEFAULT_SCHEDULER_PRIORITY
        )
        _check("reading calibration status failed")
        return {
            C.HD_CALIBRATION_OK: "ok",
            C.HD_CALIBRATION_NEEDS_UPDATE: "needs_update",
            C.HD_CALIBRATION_NEEDS_MANUAL_INPUT: "needs_manual_input",
        }.get(self._calib_status, f"unknown(0x{self._calib_status:04x})")

    @property
    def supported_calibration_styles(self) -> int:
        """Bitmask of the calibration schemes this device offers."""
        _hd.hdGetIntegerv(C.HD_CALIBRATION_STYLE, self._bufi)
        _check("reading HD_CALIBRATION_STYLE failed")
        return self._bufi[0]

    def calibration_style_names(self):
        supported = self.supported_calibration_styles
        return tuple(name for mask, name in self.CALIBRATION_STYLES
                     if supported & mask)

    def preferred_calibration_style(self):
        """The single style to pass to hdUpdateCalibration, and its name."""
        supported = self.supported_calibration_styles
        for mask, name in self.CALIBRATION_STYLES:
            if supported & mask:
                return mask, name
        return 0, "none"

    def update_calibration(self):
        """Apply a pending calibration.

        For the Touch this only takes effect while the stylus is actually
        sitting in the inkwell.
        """
        self._calib_style, _name = self.preferred_calibration_style()
        _hd.hdScheduleSynchronous(
            self._calib_update_cb, None, HD_DEFAULT_SCHEDULER_PRIORITY
        )
        _check("hdUpdateCalibration failed")

    # -- reading -----------------------------------------------------------

    def _snapshot(self, _user_data):
        """Runs in the servo thread, once per read(). Keep it short."""
        h = self.handle
        _hd.hdBeginFrame(h)

        _hd.hdGetDoublev(C.HD_CURRENT_POSITION, self._buf3)
        position = (self._buf3[0], self._buf3[1], self._buf3[2])

        _hd.hdGetDoublev(C.HD_CURRENT_VELOCITY, self._buf3)
        velocity = (self._buf3[0], self._buf3[1], self._buf3[2])

        _hd.hdGetDoublev(C.HD_CURRENT_JOINT_ANGLES, self._buf3)
        joints = (self._buf3[0], self._buf3[1], self._buf3[2])

        _hd.hdGetDoublev(C.HD_CURRENT_GIMBAL_ANGLES, self._buf3)
        gimbal = (self._buf3[0], self._buf3[1], self._buf3[2])

        _hd.hdGetDoublev(C.HD_CURRENT_FORCE, self._buf3)
        force = (self._buf3[0], self._buf3[1], self._buf3[2])

        _hd.hdGetDoublev(C.HD_CURRENT_TRANSFORM, self._buf16)
        transform = tuple(self._buf16)

        _hd.hdGetIntegerv(C.HD_CURRENT_BUTTONS, self._bufi)
        buttons = self._bufi[0]

        _hd.hdGetDoublev(C.HD_INSTANTANEOUS_UPDATE_RATE, self._buf1)
        rate = self._buf1[0]

        _hd.hdEndFrame(h)

        self._state = TouchState(
            position=position,
            velocity=velocity,
            transform=transform,
            joint_angles=joints,
            gimbal_angles=gimbal,
            force=force,
            buttons=buttons,
            update_rate=rate,
        )
        return C.HD_CALLBACK_DONE

    # State the driver reports when it has no encoder data to give: the
    # arm parked at the corner of its range with every joint at exactly
    # zero. A real arm never reads exactly zero on all three joints.
    IDLE_POSITION = (0.0, -110.0, -35.0)

    def seems_held_elsewhere(self, state: "TouchState" = None) -> bool:
        """True if another process already owns the device.

        OpenHaptics lets a second process call hdInitDevice without
        complaint, then feeds it placeholder state forever -- so a demo
        left running in another window looks exactly like a device that
        is plugged in but frozen. Check for the placeholder rather than
        letting the caller puzzle over constant readings.
        """
        s = state if state is not None else self.read()
        return (
            s.joint_angles == (0.0, 0.0, 0.0)
            and tuple(round(v, 3) for v in s.position) == self.IDLE_POSITION
        )

    def read(self) -> TouchState:
        """Take one consistent snapshot of the device."""
        # Pass the WINFUNCTYPE wrapper built in __init__, not the bound
        # method -- and keep holding the reference, or the trampoline gets
        # collected while the scheduler still has its address.
        _hd.hdScheduleSynchronous(
            self._snapshot_cb, None, HD_DEFAULT_SCHEDULER_PRIORITY
        )
        _check("reading device state failed")
        return self._state

    # -- force output ------------------------------------------------------

    def _force_tick(self, _user_data):
        """Runs on every servo tick while force output is enabled."""
        h = self.handle
        _hd.hdBeginFrame(h)
        _hd.hdSetDoublev(C.HD_CURRENT_FORCE, self._commanded_force)
        _hd.hdEndFrame(h)
        return C.HD_CALLBACK_CONTINUE

    def enable_force_output(self):
        """Start commanding force.

        Installs a 1 kHz Python callback -- see the module docstring for why
        that is heavier than reading. Call ``set_force`` to change what it
        pushes out.
        """
        if self._force_handle is not None:
            return
        _hd.hdEnable(C.HD_FORCE_OUTPUT)
        _check("hdEnable(HD_FORCE_OUTPUT) failed")
        self._force_handle = _hd.hdScheduleAsynchronous(
            self._force_cb, None, HD_DEFAULT_SCHEDULER_PRIORITY
        )
        _check("scheduling the force callback failed")

    def set_force(self, fx: float, fy: float, fz: float):
        """Set the force vector in newtons. Requires enable_force_output()."""
        self._commanded_force[0] = fx
        self._commanded_force[1] = fy
        self._commanded_force[2] = fz

    def disable_force_output(self):
        self.set_force(0.0, 0.0, 0.0)
        if self._force_handle is not None:
            _hd.hdUnschedule(self._force_handle)
            self._force_handle = None
        _hd.hdDisable(C.HD_FORCE_OUTPUT)


__all__ = [
    "TouchDevice",
    "TouchState",
    "HDError",
    "BUTTON_MASKS",
]
