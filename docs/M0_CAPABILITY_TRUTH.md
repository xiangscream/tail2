# M0 能力验证表

2026-09-20 · 当前只有静态检查、编译和无设备测试。下表的“探针已写”不代表真机通过。

| 能力 | 当前工具 | 静态依据 / 限制 | 真机状态 |
|---|---|---|---|
| Observation | snapshot；可选 HOG 人体候选 | USB/UVC，显式索引与后端；主机收帧时间单独记录 | pending |
| Device | device.list / open / status | 显式 Tail2 USB 选择；通用回调只计数；类型化回读保持原值 | pending |
| Native candidates | candidates.probe | 只找到通知枚举，没有正式列表/解码路径；工具输出静态 UNKNOWN | unknown |
| Target B | target.select / clear | Tail2 选框 API；归一化 ROI，显式 Normal zoom 有副作用 | pending |
| Track | track.set | 旧设备类别接口，须显式开启兼容探测 | pending |
| Framing | framing.set | Tail2 full/half/close/normal；配置与视觉满足分开 | pending |
| Look | look.nudge / stop / status | 有限运动，旧类别接口；需现场验证方向、停止与回读 | pending |
| Capture | capture.device | Tail2 媒体 API；尚无本次文件自动取回链 | pending |
| Record | record.start / stop | UVC 与机内录像存在手册互斥限制，当前固件待测 | pending |
| Position | position.list / recall | Tail2 上是云台视角；已有 ID 由用户确认，len 单位待查 | pending |
| Position save | position.save | 主动拒绝写入，避免覆盖已有预置 | deferred |
| Task cancel / stop_all | 契约已定义 | M1 完成调度撤销与确认；M0 仅各项原始停止探针 | not_implemented |
| Agent | 无 | M2 接视觉模型与工具循环 | not_implemented |

本地回报分别填写：请求与返回码、实际设备状态、视觉结果、真实文件结果、重复次数和失败原因。调用超时记为 unknown/indeterminate，不视作未执行。

## 推荐第一轮顺序

1. Windows 编译与只读枚举。
2. USB 图像与控制设备绑定，确认同一台相机。
3. 操作者确认可停止，才执行小幅 Look 测试。
4. 同帧候选/坐标校准，Box 选具体人，再测试 Track 与 Framing。
5. UVC 工作时的 Capture / Record 与真实文件结果。
6. 已确认的 Preset、原生候选正式接口和剩余状态路径。

详细步骤见 M0_RUNBOOK.md；脱敏结果提交 docs/handoff/inbox/。
