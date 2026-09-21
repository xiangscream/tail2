# 当前交接

2026-09-21 · Tail2 Embodied Agent MVP

当前阶段：**Tail2 SDK Truth Sweep（原语层冻结前的完整能力摸底）**

集成基线：`main`（后续功能分支一律从 main 开，PR 直接回 main）
主任务：Issue #8
M1B 子任务：Issue #11（结项）
当前计划：`../SDK_TRUTH_SWEEP_PLAN.md`
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

## M1B 真机结果（2026-09-21）

`B0/B1/B2/B3/B4` 真机 PASS，`B5/B6` fake/host path PASS。金链在真机走通；Track 内 `target.select` 切换目标全程 `completed`、不重进 Track / 不 reobserve。

真机新增限制（详见 `inbox/2026-09-21-m1b-target-track.md`）：

- human 框选在框内无可检测人脸/头时静默 no-op（返回 `completed` 但云台零位移）。
- 目标身份由设备 AI 决定；`selection=center/largest` 会锁画面中心/最大的人，漂移后可误锁旁人。
- `look.stop` 后手动云台不再动作（黄→紫灯），需经 `track.start` 重启用 AI 才恢复；`look.nudge` 钳制 `±10 dps / ≤500ms`。
- `requested_roi` 是选择帧坐标语义，设备重构图后与目标错位，勿当实时跟踪框。

## M1B 真机纪律

- 从网页端给出的 exact HEAD 新建 `local/m1b-target-track`。
- 先完成 M1B 代码和离线测试，再开设备。
- 真机 Case 按 B0→B6 顺序。
- B5/B6 的阻塞/timeout 主验证使用 fake/host path，不故意卡真实设备。
- 真实图像、raw SDK 日志、序列号留 `.local/`。
- M1B 不做 Framing / Look / record reconnect / Agent。

Issue #11：
<https://github.com/xiangscream/tail2/issues/11>


## M1B 结项裁决

M1B PASS，不再追加双人身份稳定性专项作为本阶段 blocker。

冻结语义：

- `target.select completed` = Runtime/Adapter/设备选择请求链完成；**不等于身份已被设备可靠锁定**。
- `ai_main_mode==2` = Track runtime；**不等于 healthy following**。
- gimbal yaw 变化只能作为 `motion_evidence`，不是 visual identity proof。
- `follow_health` 在没有 frame-bound visual verifier 时保持 `unknown`。
- human Box 的“框内无可检测头/脸时静默 no-op”和多人身份歧义作为设备/Perception 限制，进入后续 Target verification / M2，不阻塞 M1B。
- requested ROI 永远是选择帧坐标，不是实时 tracking box。

## Git 工作流

从本轮起恢复普通主干工作流：

`main → feature branch → PR → CI/review → main`

不再把 `kickoff/*`、`m1/*` 当长期集成主线。阶段分支/本地 Agent 分支只承担短期开发与证据回读，合格后直接进入 main。长期事实以 main 的代码、正式 docs 和 Issue 为准。


## 当前开发方向：SDK Truth Sweep

M1B 之后暂停继续扩 M1C/M1D 原语实现。先把授权的 Tail2 SDK 资源整体摸清，再做 Pro 级 Primitive Layer Architecture Freeze。

目标不是“每个 SDK 函数都包成能力”，而是让所有 Tail2-relevant 能力都有明确真值：VERIFIED / READBACK_VERIFIED / ACCEPTED_UNPROVEN / CONSTRAINED / UNSUPPORTED_TAIL2 / NO_PUBLIC_PATH / DEFERRED_UNSAFE / NOT_PRODUCT_RELEVANT。

执行顺序：

1. Phase 0：完整静态 SDK census，覆盖整个授权 SDK 包，而不是只看现有已知 API。
2. Wave A：会改变原语架构的 Gimbal / AI Control / Target View+Zoom / Zoom family。
3. Wave B：Gesture / Focus+IQ / Preset+Boot / 状态与回调。
4. Wave C：Media / Output。
5. Wave D：Unsupported / Deferred / No-public-path 收口。
6. 全部完成后，再启动 Pro 级中间原语层冻结。

Git 继续保持普通主干流程：

`main → feature/sdk-sweep-X → PR → CI/review → main`

每一 Wave 都从当时最新 main 开，不再建立长期阶段集成分支。
