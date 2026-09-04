# Touch 启动器

3D Systems Touch 全部 **46 个**厂家程序的图形启动界面。

## 怎么开

**双击项目根目录的 `Touch启动器.bat`**（它转发到这里的同名脚本）。

或者：

```bash
pythonw touch_launcher.pyw      # 无控制台窗口
python  touch_launcher.pyw      # 带控制台，出错时能看到 traceback
```

命令行版（同一份清单）：

```bash
python launch.py          # 文字菜单
python launch.py 8        # 直接跑第 8 个
python launch.py --list   # 只看清单
```

## 界面

```
┌───────────────────────────────────────────────────────────────┐
│ 3D Systems Touch 启动器            ● 设备在线 · Touch (USB,HID)│
├──────────────────────────┬────────────────────────────────────┤
│ 搜索 [______] □只看推荐★  │  牙科探针查龋齿                    │
│ ┌──────────────────────┐ │  图形程序　★ 推荐                  │
│ │ 官方上位机 / 诊断工具  │ │                                    │
│ │   ★ Touch Diagnostic │ │  拿探针在牙模上找龋洞。             │
│ │     Touch Smart Setup│ │  探针掉进龋洞的手感和滑过硬牙釉质    │
│ │ QuickHaptics 3D 演示  │ │  完全不同 —— 牙医培训靠的就是这个。 │
│ │   ★ 牙科探针查龋齿    │ │                                    │
│ │     骷髅 + 库仑力场   │ │  程序  ...\TeethCavityPickGLUT.exe │
│ │ 纯手感（无图形）      │ │  目录  ...\Quickhaptics\bin\x64    │
│ │   ★ 振动效果 [无图形] │ │                                    │
│ └──────────────────────┘ │  [ 启动 ] [关闭运行中] [打开文件夹] │
├──────────────────────────┴────────────────────────────────────┤
│ 共 46 个程序                    驱动目录 D:\...\Phantom Device │
└───────────────────────────────────────────────────────────────┘
```

- **双击列表项**或按回车 = 启动
- **搜索框**按名称和说明过滤
- **只看推荐 ★** 只显示我挑的 7 个最值得玩的
- **右上角**实时显示设备在线状态（每 8 秒后台刷新一次，不卡界面）
- **`[无图形]`** 标记 = 控制台程序，没有 3D 窗口，靠手感或看文字输出

## 文件

| 文件 | |
|---|---|
| `touch_launcher.pyw` | tkinter GUI，只用标准库，无依赖 |
| `catalog.py` | **共享清单** —— 46 个程序的路径、说明、启动规则 |
| `Touch启动器.bat` | 双击入口（内容纯 ASCII，避免 cmd 代码页乱码） |
| `launch.py` | 命令行版，读同一个 `catalog.py` |

改程序清单只需要动 `catalog.py`，GUI 和命令行会同步。

## 为什么需要启动器 —— 直接双击 exe 会失败

这三件事是实际踩出来的，`catalog.py` 里的 `build_env()` 和 `App.workdir` 全部处理了：

**1. 缺 DLL。**
`Quickhaptics\bin\x64\` 和 `examples\bin\x64\HL\` 里**只有 exe，没有任何 DLL**。
`hd.dll` / `hl.dll` / `glut32.dll` 只存在于驱动根目录。不加进 `PATH` 就是启动即闪退，
而且**不报错**。

**2. 缺 `OH_SDK_BASE` 环境变量。**
`QH.dll`（QuickHaptics 库）要读
`$(OH_SDK_BASE)/QuickHaptics/Repository/` 下的字体和错误纹理，没有就拒绝启动：

```
Found device model: Touch / serial number: <你的序列号>.
Please set the "OH_SDK_BASE" environment variable to the SensAble install directory
```

SDK 安装程序**确实**把 `OH_SDK_BASE` 设成了系统级环境变量
（`HKLM\...\Session Manager\Environment`，`REG_EXPAND_SZ`）。
但环境变量是**进程启动时**从注册表读一次的：装 SDK 之前就已经开着的终端、
IDE、资源管理器，它们的环境块里没有这个值，从它们启动的程序也就继承不到。
装完 SDK 没重启的会话，跑这些演示就会撞上那条报错。

启动器用 `env.setdefault("OH_SDK_BASE", ...)` 兜底：继承到了就用继承的，
没继承到就补一个。所以不管终端是什么时候开的都能跑。
`HL_DOP_Demo`（脊椎那个）也要它，用来找 `examples/models/LumbarBallProbe.obj`
和 `examples/textures/Spine3.tga`。

**3. 工作目录必须对。**
演示程序用**相对路径**加载模型（`models/skull.obj`、
`models/TeethCavityPickModels/dentalPick.obj`），
必须从各自的 `bin` 目录启动。

## 设备占用

**设备一次只能被一个程序占用。** 启动器一次只跑一个，运行期间「启动」按钮会禁用，
程序退出后自动恢复。

这也意味着：跑这些程序时 `code/touchpy/demo_read.py`、`demo_force.py` 必须先关掉，反之亦然。

## 换机器 / 换安装路径

`catalog.py` 会依次找 `hd.dll` 来定位驱动目录。要指定别的位置：

```bash
set TOUCH_DRIVER_ROOT=X:\path\to\Phantom Device Drivers
```

## 退出码

GLUT 演示程序用 Esc 或点 × 关闭时经常返回非零退出码，**这不是错误**，
状态栏会照实显示。
