# M0 本地执行手册

目标：用真实 Tail2 回答 SDK 可以做什么、怎样知道它做成了。全程人在现场；保持云台周围空间；关闭会同时控制设备的 OBSBOT Center/其他客户端。官方工具可用于预先配置和人工对照，测试时避免抢占控制或 UVC。

## 1. 准备与离线验证

使用 Windows x64、Python 3.11/3.12、Visual Studio C++ 桌面开发工具、CMake、Boost 1.75+ 头文件和用户已有 SDK。SDK 放仓库外；不要下载陌生 DLL。

```powershell
git fetch origin
git switch kickoff/embodied-m0-20260920
git switch -c local/m0-hardware
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[vision]"
.\tools\build_windows.ps1 -SdkRoot 'C:\private\libdev_v2.1.0_8' -BoostRoot 'C:\deps\boost'
python tools/sdk_audit.py --sdk 'C:\private\libdev_v2.1.0_8'
```

`build_windows.ps1` 选择 Release SDK / x64；原生测试在不连接设备时也可运行。记录编译器、Python、OpenCV、SDK hash；新版本不沿用旧测试结论。

## 2. 默认只读枚举

```powershell
python -m tail2_mvp probe --bridge .\build\Release\tail2_probe.exe --trace .local/run-01
```

自动执行 hello 与 device.list。只接受 Tail2 + USB 模式；打印出的序列号和设备路径属于本地信息，不能复制到公共 issue。输入：

```json
{"op":"candidates.probe"}
{"op":"device.list","args":{"wait_ms":5000}}
```

candidates.probe 返回本轮静态核对结论 UNKNOWN，**没有偷偷做候选订阅**。

退出：Windows 控制台 EOF 或 Ctrl+C。设置本地序列号后重开：

```powershell
$env:TAIL2_DEVICE_SN='YOUR_LOCAL_SERIAL'
python -m tail2_mvp probe --bridge .\build\Release\tail2_probe.exe --trace .local/run-02
```

输入 `{"op":"device.status"}`，记录 typed SDK 回读和回调计数。空值表示没法确认，不能改成成功。每次运行使用新的 trace 目录，避免多进程写同一文件。

## 3. USB 图像与设备绑定

明确 Tail2 的视频设备索引，不能假设 index 0。结合 Windows 设备名称、SDK video_path 与实际画面核对。使用不会涉及隐私的测试场景。

```powershell
python -m tail2_mvp snapshot --index 1 --backend dshow
```

`1` 仅为示例，必须换成现场索引。打不开可单独测试 msmf；记录后端，不同时运行多个图像消费者。结果写入 `.local/observations/<id>/`，包括 frame.jpg 和 observation.json。工具超时只表示没有取得可用帧。

候选台架测试：

```powershell
python -m tail2_mvp snapshot --index 1 --backend dshow --human-candidates
```

HOG 是可选的人体基线；只返回候选，没有语义 Agent。不要把空候选写成“画面里无人”。

验证 SDK ROI 与图像坐标：横屏无镜像起步，在左/中/右放置目标，确认归一化原点、边界及实际画面一致；再验证镜像/竖屏/变焦发生变化时旧坐标是否失效。M0 输出的 mapping 状态保持 UNVERIFIED，校验结果需人工回报，M1 再接自动准入。

## 4. 先证明停止，再进行运动和目标测试

新开受控实例：

```powershell
python -m tail2_mvp probe --bridge .\build\Release\tail2_probe.exe --allow-control --allow-legacy-probes --trace .local/run-03
```

开始前在官方控制端验证人工停止方式，然后退出官方端。以下旧类别 SDK 在 Tail2 的适用性未证实，逐项手动执行：

```json
{"op":"look.stop"}
{"op":"look.status"}
{"op":"track.set","args":{"enabled":false}}
```

确认设备确实停止，再试非常小幅的运动：

```json
{"op":"look.nudge","args":{"pan_dps":1,"pitch_dps":0,"duration_ms":100}}
{"op":"look.stop"}
{"op":"look.status"}
```

探针限制为 ±10 dps、最多 500 ms，属于台架设置。正常 SDK 返回后会发送零速；SDK 卡住时没有独立硬件看门狗，主机超时不能保证停机。出现异常即停止自动实验并现场处理，不能循环重试。

## 5. Box → 具体对象 → 跟踪 → 构图

两名知情参与者先保持相对静止。用刚取得且校准通过的画面确定其中一个目标区域。以下框只展示格式，**必须替换为现场真实目标框**：

```json
{"op":"target.select","args":{"class":"human","x1":0.1,"y1":0.15,"x2":0.4,"y2":0.95}}
{"op":"device.status"}
{"op":"framing.set","args":{"mode":"full_body"}}
{"op":"device.status"}
```

记录：选框是否即开启 Tracking；是否选对对象；是否改变 zoom；Framing 配置和画面是否一致。M0 明确设置 Normal zoom，因此再次 framing.set 是必要步骤。若需要单独 track.set，先记录选框原有行为再测试。

观察目标小幅左右移动，再测试 `half_body`、`close_up`、`normal`。关跟踪用 track.set(false)，清目标用 target.clear，两者真实含义分别核对。不将 callback_count 增加当作选人成功。

## 6. Capture / Record：优先查输出模式冲突

手册 v1.0 指出 UVC 与机内录像互斥。保持现场模式，分别探测；不得为了通过测试自动切换输出模式。

```json
{"op":"capture.device"}
{"op":"device.status"}
{"op":"record.start"}
{"op":"device.status"}
{"op":"record.stop"}
{"op":"device.status"}
```

必须同时记录：SD 卡是否存在、SDK 返回、官方端对照、是否真实产生文件、文件能否取回/播放。该 getter 的 operation 值仅供核对，不表示文件已经 finalized。

若 UVC 下录像不可用，回报 `unavailable_in_uvc`。建议由产品确认 PC-UVC capture/record Provider 后再实现；USB 快照可用于观察，但不得计作机内照片测试通过。

## 7. Preset 与候选列表

`position.list` 只输出原始 len 与固定上限槽位，len 单位尚未确认。`position.save` 主动拒绝执行，防止覆盖已有机位。仅在用户明确指认现有预置 ID 后测试 `position.recall`，观察到位、Tracking 状态和设置保留范围。

原生候选只查文档化路径。询问 SDK Owner：AiTarget 通知的订阅方式、payload、列表是否包含全部候选、时间戳、坐标空间、Tail2/UVC 支持。无法确认就保留 UNKNOWN，后续走 PC Provider。

## 8. 状态页

另一个终端：

```powershell
python -m tail2_mvp status --trace .local/run-03 --port 0
```

按控制台打印的本机 URL 打开。只读页展示请求、SDK 调用和返回状态，当前明确标注 Agent 未接入。图像标框和模型决策展示在 M2 接入。

## 9. 回报格式

在 docs/handoff/inbox/ 新建一份 Markdown 摘要，并链接 PR / issue：

- 使用的准确 commit、系统/编译器/Python/SDK hash、设备固件；设备号只写本地 alias。
- 每项操作：SDK 声明 → 命令是否接受 → 实际设备行为 → 回读来源 → 视觉或文件结果 → 未解决问题。
- 坐标/镜像/旋转/UVC 绑定、候选来源、媒体模式、停机与控制权试验的结论。
- 测试次数、失败次数、人工干预；原始日志路径只留本地，公开文档使用占位 alias。
- 需要修复的代码单独提交，重新测试。发布前 `git diff --check`、unittest、`python tools/public_check.py`，再人工检查媒体/密钥/序列号/SDK 内容。

M0 结束依据是完整、真实的能力表。部分能力 unavailable 可以进入下一步设计，不能把 UNKNOWN 换成成功。
