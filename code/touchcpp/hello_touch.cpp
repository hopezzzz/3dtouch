/* Minimal OpenHaptics HD program: open the Touch, print its state, exit.
 *
 * The point of this file is to be the smallest thing that proves the C++
 * toolchain, the headers, the import library and the device all line up.
 * Build it with build.bat, then grow it into whatever you need.
 *
 * The HD API drives the device from a real-time servo loop in its own
 * thread. Application code never touches that thread directly: it hands
 * the scheduler a callback, and the scheduler runs it between servo
 * ticks. hdScheduleSynchronous blocks until the callback has run, which
 * is how you take a consistent snapshot -- reading the state fields from
 * the main thread instead would tear across servo updates.
 */

#include <cstdio>
#include <windows.h>   /* Sleep */
#include <HD/hd.h>

struct Snapshot {
    HDdouble position[3];        /* mm */
    HDdouble jointAngles[3];     /* rad, the three arm joints */
    HDdouble gimbalAngles[3];    /* rad, the three stylus joints */
    HDdouble transform[16];      /* 4x4, column-major */
    HDdouble updateRate;         /* Hz, the servo loop's own estimate */
    HDint    buttons;            /* bitmask */
};

/* Runs in the servo thread. Keep it short: everything here delays the
 * next servo tick. */
HDCallbackCode HDCALLBACK snapshotCallback(void *userData)
{
    Snapshot *s = static_cast<Snapshot *>(userData);
    HHD hHD = hdGetCurrentDevice();

    hdBeginFrame(hHD);
    hdGetDoublev(HD_CURRENT_POSITION,           s->position);
    hdGetDoublev(HD_CURRENT_JOINT_ANGLES,       s->jointAngles);
    hdGetDoublev(HD_CURRENT_GIMBAL_ANGLES,      s->gimbalAngles);
    hdGetDoublev(HD_CURRENT_TRANSFORM,          s->transform);
    hdGetDoublev(HD_INSTANTANEOUS_UPDATE_RATE, &s->updateRate);
    hdGetIntegerv(HD_CURRENT_BUTTONS,          &s->buttons);
    hdEndFrame(hHD);

    return HD_CALLBACK_DONE;
}

static bool failed(const char *what)
{
    HDErrorInfo error = hdGetError();
    if (!HD_DEVICE_ERROR(error))
        return false;
    std::fprintf(stderr, "%s: %s (0x%04x, internal %d)\n",
                 what, hdGetErrorString(error.errorCode),
                 error.errorCode, error.internalErrorCode);
    if (error.errorCode == HD_TIMER_ERROR || error.errorCode == HD_INVALID_VALUE)
        std::fprintf(stderr,
                     "  The device is probably already open in another "
                     "program.\n  Only one program can hold it at a time.\n");
    return true;
}

int main()
{
    HHD hHD = hdInitDevice(HD_DEFAULT_DEVICE);
    if (failed("hdInitDevice"))
        return 1;

    std::printf("model      : %s\n", hdGetString(HD_DEVICE_MODEL_TYPE));
    std::printf("vendor     : %s\n", hdGetString(HD_DEVICE_VENDOR));
    std::printf("serial     : %s\n", hdGetString(HD_DEVICE_SERIAL_NUMBER));
    std::printf("driver     : %s\n", hdGetString(HD_VERSION));

    HDdouble maxForce = 0.0;
    hdGetDoublev(HD_NOMINAL_MAX_FORCE, &maxForce);
    std::printf("max force  : %.2f N\n\n", maxForce);

    hdStartScheduler();
    if (failed("hdStartScheduler")) {
        hdDisableDevice(hHD);
        return 1;
    }

    /* hdStartScheduler returns before the servo loop has finished its
     * first frame. Opening a frame in that window fails with
     * HD_ILLEGAL_END ("hdEndFrame without a matching hdBeginFrame"), and
     * a sample that does slip through carries uninitialised state rather
     * than a real reading.
     *
     * A fixed number of throwaway frames is not enough -- how long the
     * loop takes to come up varies. Poll until several land clean in a
     * row, draining the error stack as we go. */
    Snapshot s = {};
    int clean = 0;
    for (int attempt = 0; attempt < 600 && clean < 3; ++attempt) {
        s.updateRate = 0.0;
        hdScheduleSynchronous(snapshotCallback, &s, HD_DEFAULT_SCHEDULER_PRIORITY);

        HDErrorInfo error = hdGetError();
        if (!HD_DEVICE_ERROR(error) && s.updateRate > 0.0) {
            ++clean;
        } else {
            clean = 0;
            while (HD_DEVICE_ERROR(hdGetError())) { }   /* drain */
        }
        Sleep(5);
    }

    if (clean < 3) {
        std::fprintf(stderr, "the servo loop did not come up\n");
        hdStopScheduler();
        hdDisableDevice(hHD);
        return 1;
    }

    hdScheduleSynchronous(snapshotCallback, &s, HD_DEFAULT_SCHEDULER_PRIORITY);
    if (failed("reading device state")) {
        hdStopScheduler();
        hdDisableDevice(hHD);
        return 1;
    }

    std::printf("position   : %8.2f %8.2f %8.2f  mm\n",
                s.position[0], s.position[1], s.position[2]);
    std::printf("joints     : %8.4f %8.4f %8.4f  rad\n",
                s.jointAngles[0], s.jointAngles[1], s.jointAngles[2]);
    std::printf("gimbal     : %8.4f %8.4f %8.4f  rad\n",
                s.gimbalAngles[0], s.gimbalAngles[1], s.gimbalAngles[2]);
    std::printf("buttons    : 0x%x\n", s.buttons);
    std::printf("servo loop : %.0f Hz\n", s.updateRate);

    hdStopScheduler();
    hdDisableDevice(hHD);
    return 0;
}
