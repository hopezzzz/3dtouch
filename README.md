# 3D Systems Touch

3D Systems Touch 力反馈设备的 Python / C++ 接口，外加一个能跑通厂家全部 46 个程序的启动器。

Touch 是 6 自由度力反馈输入设备（原 Sensable Phantom Omni / Geomagic Touch 系列）：
读笔尖的位置和姿态，也能反过来对你的手输出力。

| | |
|---|---|
| 支持型号 | Touch（USB，HID 或 CDC 固件）、Touch X |
| 输出力 | 3.3 N（Touch 标称最大值） |
| 工作空间 | ±80 × ±60 × ±35 mm |
| 伺服环 | 1000 Hz |

## 环境要求

- Windows 10 / 11
- **64 位 Python 3.8+**（`hd.dll` 是 x64；32 位 Python 会加载失败并给出说明）
- 只写 C++ 才需要：Visual Studio（含 C++ 工作负载）

Python 侧**除标准库外零依赖**，不用 pip 装任何东西。

## 快速开始

**1. 装驱动和 SDK** —— 双击 `install\一键安装.bat`

从 3D Systems 官方源下载（约 280 MB），逐个做 SHA-256 校验和 Authenticode 签名验证，
然后依次运行两个安装程序：

| | 装到哪 |
|---|---|
| **驱动** | 它自己的默认路径 —— 它要往 Windows 驱动库注册，**别改**。装完重启 |
| **SDK** | 预填成本项目下的 `OpenHaptics/`，跟代码放一起 |

两个向导都会正常弹出，SDK 那个的路径已经填好，点 Next 即可。SDK 装哪其实都行，
代码靠环境变量 `OH_SDK_BASE` 找它（安装程序会自动设）。

**不想跑脚本**就看 [install/手动安装.md](install/手动安装.md) ——
官方直链、安装步骤、校验值、故障排查都在里面。

**只想读数据的话，SDK 可以不装** —— `code/touchpy` 只需要驱动。
SDK 是给那 40 个演示程序和 C++ 开发用的。

**2. 校准** —— 把笔杆放进墨盒（底座上的笔架凹槽）

```cmd
python code\touchpy\check_device.py    :: 先确认链路通
python code\touchpy\calibrate.py       :: 校准
```

**3. 用起来**

```cmd
Touch启动器.bat                        :: 玩厂家的 46 个程序
python code\touchpy\demo_read.py       :: 实时读位置/姿态/关节角/按钮
```

## 目录

```
3dtouch/
├─ Touch启动器.bat     打开厂家程序启动器
├─ install/            装驱动和 SDK（自动脚本 + 手动说明）
├─ code/
│   ├─ launcher/       厂家程序启动器（图形 + 命令行）
│   ├─ touchpy/        Python 接口和示例
│   └─ touchcpp/       C++ 起点
├─ OpenHaptics/        SDK 本体（装完才有，不在仓库里）
└─ vendor/             安装包和官方文档（下载后才有，不在仓库里）
```

仓库里只有 `code/`、`install/` 和 `Touch启动器.bat`。**`OpenHaptics/` 和 `vendor/` 不随仓库分发** ——
OpenHaptics Developer Edition 的授权明确禁止再分发
（`OpenHaptics/docs/OpenHapticsDeveloperEditionLicense.txt` 第 2 节：
"the Authorized User may not use, copy, modify, or distribute the Software"），
而且两个安装包都超过 GitHub 的 100 MB 单文件上限。所以用脚本从官方源拉。

### `code/touchpy/` — Python 接口

`ctypes` 直接调 OpenHaptics 的 HD API，不用编译任何东西。

```python
from touch_hd import TouchDevice

with TouchDevice() as dev:
    s = dev.read()
    print(s.position)       # (x, y, z)，单位 mm
    print(s.joint_angles)   # 三个手臂关节，弧度
    print(s.gimbal_angles)  # 三个笔杆关节，弧度
    print(s.orientation)    # 3x3 旋转矩阵
    print(s.buttons_down)   # 例如 (1, 2)
```

输出力：

```python
dev.enable_force_output()
dev.set_force(0.0, 1.5, 0.0)   # 牛顿
```

细节和踩过的坑见 [code/touchpy/README.md](code/touchpy/README.md)。

### `code/launcher/` — 厂家程序启动器

驱动和 SDK 一共带了 46 个程序：诊断上位机、QuickHaptics 3D 演示
（牙科探针、骷髅力场、可变形表面…）、OpenHaptics 的 HD/HL 示例。

**直接双击那些 exe 大多会失败** —— 缺 DLL、缺 `OH_SDK_BASE`、工作目录不对。
启动器把这三件事都处理了。见 [code/launcher/README.md](code/launcher/README.md)。

### `code/touchcpp/` — C++ 起点

一个能编能跑的最小 HD API 程序，加 `build.bat` / `run.bat`。

编译时**必须加 `/D WIN32`**：`hdExport.h` 把 `HDAPI` / `HDAPIENTRY` 的定义包在
`#if defined(WIN32)` 里，而现代 MSVC 只定义 `_WIN32`（`WIN32` 是 VS 工程模板加的）。
少了它，每个 HD 函数原型都会塌成"缺少类型说明符"。
见 [code/touchcpp/README.md](code/touchcpp/README.md)。

## 常用命令

```cmd
:: 厂家程序
Touch启动器.bat
python code\launcher\launch.py            :: 文字菜单
python code\launcher\launch.py --list     :: 只看清单

:: Python
python code\touchpy\check_device.py       :: 分级诊断：驱动 → USB → HD API
python code\touchpy\calibrate.py          :: 每次设备上电后跑一次
python code\touchpy\demo_read.py          :: 实时读数
python code\touchpy\demo_read.py --csv log.csv --rate 200
python code\touchpy\buttons.py            :: 实时按钮状态
python code\touchpy\demo_force.py         :: 力反馈：一面摸得到的虚拟地板

:: C++
cd code\touchcpp
build.bat
run.bat

:: 安装
install\一键安装.bat                       :: 下载 + 安装
install\一键安装.bat --download-only       :: 只下载，安装包自己去点
install\一键安装.bat --sdk-dir C:\OpenHaptics
install\一键安装.bat --check               :: 校验已下载的文件
```

## 两条必须记住的规则

**1. 设备一次只能被一个程序占用。**

跑厂家演示时 `touchpy` 的脚本必须先关掉，反之亦然。冲突有两种表现：

- `hdStartScheduler` 直接失败（`0x0304`）
- **看起来打开成功，但读数永远是占位值**（关节角全 0、位置 `(0, -110, -35)`）

后者尤其坑 —— 看着像设备坏了。`touch_hd.py` 的 `seems_held_elsewhere()` 专门检测这个。

**2. 每次设备上电后要校准一次。**

编码器是增量式的，上电后驱动不知道手臂在哪。把笔杆放进墨盒，跑
`python code\touchpy\calibrate.py`，或者用驱动自带的 `Touch_SmartSetup.exe`。
**没校准之前坐标是偏的，力的方向也是错的。**

## 找不到驱动或 SDK 时

代码不写死路径：

| | 怎么找 |
|---|---|
| 驱动 | 按顺序在几个常见位置找 `hd.dll`。可用 `TOUCH_DRIVER_ROOT` 指定 |
| SDK | 先读 `OH_SDK_BASE`（安装程序会设），再回退到项目内的 `OpenHaptics/` 和几个标准路径 |

装完之后要**新开一个终端**才能拿到新的环境变量 —— 进程只在启动时读一次注册表，
装 SDK 之前就开着的窗口拿不到 `OH_SDK_BASE`。

## 授权

`code/` 下的代码你随意使用。

驱动、SDK、官方文档的版权归 3D Systems，本仓库不包含也不分发它们。
SDK 装的是 **Developer Edition**，科研教学可用；**做成产品对外分发需要向
3D Systems 购买商业授权**。
