# 当前交接

2026-09-21 · Tail2 Embodied Agent MVP

当前阶段：**M1 Capability Runtime / M1B Target + Track**

开发分支：`m1/capability-runtime`
主任务：Issue #8
M1B 子任务：Issue #11
M0/M0.5 结项基线：`704b7fc2054e85d850ec2969964a17abc307cad3`

## 已完成：M1A Runtime Foundation

PR #10 已合入 M1 开发分支。M1A 已提供：

- `CapabilityRequest / CapabilityResult / CapabilityError` 与正式生命周期；
- `REOBSERVE_REQUIRED` continuation；
- requested / sdk_reported / visual_check / artifact 证据分层；
- StateRegistry last-good / stale；
- ResourceOwnership + SingleWriter；
- task/request 级取消；
- cooperative deadline，剩余时间传入 Observer / bridge；
- side-effect timeout → indeterminate；
- RuntimeSession bridge failure rebuild；
- rebuild 时 Observer / ObservationStore / calibration / selected / ROI / track / framing 失效；
- 薄 Tail2Adapter，调用侧不接触 SDK。

M1A 报告：
`inbox/2026-09-21-m1a-runtime-foundation.md`

## 已冻结设备事实

- Observation：单 UVC 属主，frame-bound Observation / Candidate / epoch。
- Target/Track：Normal 下 Box 不启动跟踪；先进入 Track runtime，再 Box 具体目标。
- Track entry：Center/Largest 或设备端手势；当前 canonical readback 为 `ai_main_mode`。
- `ai_main_mode==2` 只表示 Track runtime，不自动等于 healthy following。
- ROI：当前 640×480 / 1x / 横向 profile 下 identity VERIFIED；双目标 target-switch 已排除 Center 假阳性。
- Look/AI：手动云台会关 AI；恢复跟随必须显式恢复 AI/Track。
- Framing：显式 zoom 有效；已试 Offset 路径没有有效 Tail2 构图偏移结果。
- Media：MVP 默认 host_uvc。
- 无 native candidate list / tracking bbox。

## 当前任务：M1B Target + Track 金链

正式目标：

`Observation → semantic target → prepare Track → REOBSERVE → reground → Box → verify follow`

本轮需要：

1. 正式 Track state：runtime_mode / ai_requested / follow_health。
2. track.start 显式确保 AI enabled；进入 Track 后返回 REOBSERVE_REQUIRED。
3. continuation 保留语义目标引用，不复用旧 bbox。
4. first-class observation_id + candidate/bbox；stale reference 零设备写。
5. 最小 Runtime 真机 harness：CapabilityRuntime → Tail2Adapter → Observer → RuntimeSession → bridge。
6. 双目标 A↔B 切换通过正式 Capability API 回归。
7. caller/test script 不出现 SDK 名。

完整开发与真机矩阵见 Issue #11。

## M1B 真机纪律

- 从网页端给出的 exact HEAD 新建 `local/m1b-target-track`。
- 先完成 M1B 代码和离线测试，再开设备。
- 真机 Case 按 B0→B6 顺序。
- B5/B6 的阻塞/timeout 主验证使用 fake/host path，不故意卡真实设备。
- 真实图像、raw SDK 日志、序列号留 `.local/`。
- M1B 不做 Framing / Look / record reconnect / Agent。

Issue #11：
<https://github.com/xiangscream/tail2/issues/11>
