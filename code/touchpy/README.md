# touchpy — 3D Systems Touch 的 Python 接口

用 `ctypes` 直接调 OpenHaptics 的 HD API（`hd.dll`），不需要编译任何东西。

## 环境

只需要两样：**Touch 驱动**（`hd.dll` 从那里加载）和 **64 位 Python 3.8+**。
除标准库外没有任何依赖。

**运行时不需要 SDK** —— `hd_constants.py` 已经生成好放在仓库里了。
SDK 只在重新生成常量时才用得上。

`touch_hd.py` 按顺序在几个常见位置找 `hd.dll`，覆盖了驱动的默认安装路径；
装到别处就设环境变量 `TOUCH_HD_DIR`。

## 文件

| 文件 | 作用 |
|---|---|
| `touch_hd.py` | HD API 的 ctypes 封装，`TouchDevice` / `TouchState` |
| `hd_constants.py` | **自动生成**，勿手改 |
| `gen_constants.py` | 从 SDK 头文件重新生成上面那个文件 |
| `check_device.py` | 分级诊断：驱动 → USB 枚举 → HD API |
| `buttons.py` | 实时按钮状态；`--identify` 引导识别哪个物理按钮对应哪一位 |
| `calibrate.py` | 把笔杆放进墨盒完成校准 |
| `demo_read.py` | 实时读位置、姿态、关节角、按钮 |
| `demo_force.py` | 力反馈：一面摸得到的虚拟地板 |

## 用法

```bash
cd code\touchpy

python check_device.py          # 先跑这个，确认链路通
python check_device.py --watch  # 插拔时实时看设备上线/掉线

python calibrate.py             # 每次设备上电后跑一次

python demo_read.py             # 实时读数
python demo_read.py --csv log.csv --rate 200
python demo_read.py --raw       # 每行一个样本，方便管道处理

python demo_force.py            # 力反馈演示
```

自己写代码：

```python
from touch_hd import TouchDevice

with TouchDevice() as dev:
    print(dev.info())

    state = dev.read()
    print(state.position)       # (x, y, z)，单位 mm
    print(state.joint_angles)   # 三个手臂关节，弧度
    print(state.gimbal_angles)  # 三个笔杆关节，弧度
    print(state.orientation)    # 3x3 旋转矩阵
    print(state.button(1))      # 笔上按钮 1 是否按下
    print(state.buttons_down)   # 例如 (1, 2)
```

输出力：

```python
with TouchDevice() as dev:
    dev.enable_force_output()
    dev.set_force(0.0, 1.5, 0.0)   # 牛顿
    ...
    dev.disable_force_output()
```

单位遵循 HD API：**位置 mm，角度弧度，力牛顿**。

## 设计上要注意的一点

HD API 有一个独立的 **1 kHz 实时伺服线程**。两种拿数据的方式代价差很多：

- **`read()`** 走 `hdScheduleSynchronous` —— 回调在伺服线程里只跑一次，拷贝几个 double 就返回。
  几百 Hz 轮询也不会影响伺服环。**读数据用这个。**

- **`enable_force_output()`** 装的是 `hdScheduleAsynchronous` 回调，伺服线程每秒调它 1000 次。
  这意味着一个实时线程每秒抢 1000 次 GIL。能用，但回调里不能有任何内存分配
  （所以 `touch_hd.py` 里所有缓冲区都在 `__init__` 里一次性分配好），
  而且主线程一忙，`HD_INSTANTANEOUS_UPDATE_RATE` 就会掉下来 —— demo 界面上有这个读数，可以盯着看。

**只有输出力才需要那个异步回调，读数据不需要。**

## 踩过的坑（都已在代码里处理）

**1. 校准相关的调用必须在伺服线程里。**
`hdCheckCalibration()` 和 `hdUpdateCalibration()` 在主线程直接调**不报错，但永远不生效** ——
状态会一直停在 `needs_update`。SDK 自带的 `examples/HD/console/Calibration/Calibration.c`
把两者都包在 `hdScheduleSynchronous` 回调里，状态查询还要额外包一层
`hdBeginFrame`/`hdEndFrame`。本项目照做。

**2. `hdStartScheduler()` 返回时伺服环还没跑起来。**
在那个窗口里开帧会报 `HD_ILLEGAL_END`（"hdEndFrame without a matching hdBeginFrame"），
而侥幸挤进去的第一个样本拿到的是未初始化的默认值 `(0.0, -110.0, -35.0)`，
不是真实位置。`TouchDevice.open()` 里的 `_wait_until_ready()` 会轮询直到连续三帧干净
才返回，并清空错误栈。实测 15 次冷启动 0 失败。

**3. 校准是每个进程一次。**
`hdInitDevice()` 之后状态是 `needs_update`，需要在笔位于墨盒中时调一次
`update_calibration()` 才变 `ok`。`calibrate.py` 就是干这个的。

**4. `hdUpdateCalibration()` 要传单个 style，不是位掩码。**
用 `hdGetIntegerv(HD_CALIBRATION_STYLE)` 查支持哪些，然后按
AUTO > INKWELL > ENCODER_RESET 的优先级挑一个（跟 SDK 示例一致）。Touch 报的是 `inkwell`。

## 官方上位机（在驱动目录里）

| 程序 | 用途 |
|---|---|
| `Touch_SmartSetup.exe` | 校准 + 球体/立方体验证测试 + 保存配置（说明书第 4–6 步） |
| `Touch_Diagnostic_LegacyVersion.exe` | 诊断台：关节角、编码器、力输出、按钮 |
| `AdvancedHIDTouchConfig.exe` | HID 固件版设备的高级配置 |
| `TouchDemo.exe` | 官方力反馈演示 |

**首次使用必须跑一次 `Touch_SmartSetup.exe`**：把笔杆插进墨盒完成校准，然后
Save Configuration。没保存配置的话 `hdInitDevice()` 可能找不到设备，
或者读出来的坐标系是错的。

## 重新生成常量

换了 SDK 版本之后：

```bash
python gen_constants.py "..\..\OpenHaptics\include"   :: 路径按你 SDK 实际位置
```

之所以从头文件生成而不是手抄：`HD_CURRENT_POSITION` 这类是十六进制枚举，
抄错一位不会报错，只会安静地读出另一个字段。

## C++ 那边

SDK 自带源码示例和文档：

- `..\..\OpenHaptics\examples\`
- `..\..\OpenHaptics\docs\`
- `..\..\vendor\docs\OpenHaptics_Toolkit_ProgrammersGuide.pdf`
