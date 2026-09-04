# touchcpp — C++ 二次开发

OpenHaptics 就是个开发 SDK，那 46 个程序只是它的示例。这里是一个能编能跑的最小起点。

## 编译运行

```cmd
build.bat     :: 编译
run.bat       :: 运行（自动把 hd.dll 所在目录加进 PATH）
```

实测输出：

```
model      : Touch
vendor     : 3D Systems Inc.
serial     : <你的序列号>
driver     : 3.50.0
max force  : 3.30 N

position   :     0.13   -65.56   -88.24  mm
joints     :  -0.0016   0.2681  -0.3720  rad
gimbal     :   0.0001   0.7986  -1.3307  rad
buttons    : 0x0
servo loop : 1046 Hz
```

## 工具链（这台机器上已确认可用）

| | |
|---|---|
| MSVC | 14.37.32822（VS 2022）或更新 |
| Windows SDK | 10.0.22621 |
| 头文件 | `<OH_SDK_BASE>\include\HD\`、`\HL\` |
| 链接库 | `<OH_SDK_BASE>\lib\x64\Release\hd.lib`、`hl.lib` |
| 辅助库 | `<OH_SDK_BASE>\utilities\lib\x64\Release\` — `hdu.lib`、`hlu.lib`、`glut32.lib`、`SnapConstraints.lib` |

CMake 和 Ninja 也在 PATH 上，想用 CMake 组织工程也行。

## 两个坑

**1. 必须定义 `WIN32`，否则编不过。**

`hdExport.h` 把整个 Windows 分支包在 `#if defined(WIN32)` 里，`HDAPI`（`__declspec(dllimport)`）
和 `HDAPIENTRY`（`__stdcall`）都在那里面。**现代 MSVC 只定义 `_WIN32`，不定义 `WIN32`** ——
`WIN32` 历来是 Visual Studio 工程模板加的。少了它，每个 HD 函数原型都会塌成
"缺少类型说明符" 的一片错误。

所以 `build.bat` 里有 `/D WIN32`。用官方 `.vcxproj` 不会碰到这个问题，因为模板已经定义了。

**2. 系统里有两个 `hd.dll`，版本不同。**

| 版本 | 位置 | 谁装的 |
|---|---|---|
| 3.50.0 | `C:\Windows\System32\hd.dll` | OpenHaptics SDK |
| 3.4.0 | `<驱动目录>\hd.dll` | Touch 驱动 |

Windows 的搜索顺序是**应用目录 → System32 → PATH**，所以 C++ 程序拿到的是
System32 那份 3.50.0，`run.bat` 往 PATH 里塞驱动目录也改不了。

`code/touchpy` 用的是**完整路径**加载（`ctypes.WinDLL(完整路径)`），拿到的是驱动那份 3.4.0。
两个都能正常工作，但要知道 Python 和 C++ 用的不是同一个 DLL。
要强制 Python 用哪个，设环境变量 `TOUCH_HD_DIR`。

## 伺服环启动竞态

`hdStartScheduler()` 返回时伺服环还没跑完第一帧。那个窗口里开帧会报
`HD_ILLEGAL_END`（`hdEndFrame` 找不到配对的 `hdBeginFrame`），侥幸挤进去的样本
拿到的是未初始化状态。

固定次数的预热不够用 —— 启动耗时是变的。`hello_touch.cpp` 里的做法是
**轮询到连续三帧干净为止**，中间清空错误栈。`code/touchpy/touch_hd.py` 的
`_wait_until_ready()` 是同一个思路。

## 两层 API

| | |
|---|---|
| **HD**（底层） | 直接控制伺服环：读原始状态、下发力和关节力矩。循环自己管。要做数据采集、自定义控制律用这层。头文件 `HD/hd.h` |
| **HL**（高层） | 类 OpenGL 的触觉渲染：描述形状和材质，它算力。要做"能摸的 3D 场景"用这层，省掉自己写碰撞和力模型。头文件 `HL/hl.h` |
| **QuickHaptics** | 最高层，二十来行就能搭个能摸的场景。`Quickhaptics\header\` |

`hello_touch.cpp` 走的是 HD 层。

## 直接改官方示例

比从零写更快 —— 源码和 VS 解决方案都在：

```
<OH_SDK_BASE>\examples\HD\console\ConsoleExamples_VS2017.sln
<OH_SDK_BASE>\examples\HD\graphics\GraphicsExamples_VS2017.sln
<OH_SDK_BASE>\examples\HL\console\ConsoleExamples_VS2017.sln
<OH_SDK_BASE>\examples\HL\graphics\GraphicsExamples_VS2017.sln
<OH_SDK_BASE>\Quickhaptics\examples\QuickHapticsExamples2017.sln
```

一共 58 个 `.vcxproj`。VS2017 格式，VS2022 打开会提示升级工具集，同意即可。

值得先读的：

| | |
|---|---|
| `examples\HD\console\QueryDevice\` | 怎么读全部状态 |
| `examples\HD\console\Calibration\` | 校准的正确写法（`code/touchpy/calibrate.py` 就是照它写的） |
| `examples\HD\console\AnchoredSpringForce\` | 最简单的力输出 |
| `examples\HL\graphics\HapticMaterials\` | 材质参数怎么调 |
| `Quickhaptics\examples\pickApples\` | 触碰事件 + 按钮事件 |

## 授权

SDK 装的是 **Developer Edition**，每次运行都会打印：

```
This is the DEVELOPER EDITION of OPENHAPTICS,
commercial distribution is prohibited
```

科研和教学用没问题。**要做成产品对外分发，得找 3D Systems 买商业授权**
（`hdDeploymentLicense()` 这个 API 就是干这个的）。
