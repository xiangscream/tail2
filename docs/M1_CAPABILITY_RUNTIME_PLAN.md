# M1 Capability Runtime 开发计划

2026-09-21 · 基线：M0/M0.5 已结项。主任务见 Issue #8。

## 1. 目标

把 Tail2 已验证的设备行为收进一套稳定、可组合、可观察的中层能力。M1 不接 LLM；先用确定性脚本证明同一套 Capability 可以可靠完成多步任务。M2 再把这些能力作为多模态 Agent 的工具面。

核心原则：

- **语义解耦，执行接受现实耦合**：Target / Track / Framing / Look 对上层分开，Tail2 Adapter 负责处理底层副作用。
- **世界变化就重新观察**：设备状态转换、云台运动、zoom、重连后不复用旧 bbox。
- **状态不伪造**：requested、SDK readback、visual check、artifact 分开。
- **单写者**：设备控制、UVC、媒体和 Look ownership 都有唯一所有者。
- **Agent 不知道 SDK**：M1 上层测试与脚本中不出现厂商 API 名。

## 2. 已冻结事实

- UVC 由单一 Observation Service 持有。
- 当前 640×480 / 1x / 横向 profile 的 UVC→SDK ROI 是 **identity VERIFIED**，双目标 target-switch 已验证。
- Normal 下 Box 不启动跟踪；进入 Track runtime 后 Box 才能指定具体目标。
- Center/Largest 会进入 Track runtime 并移动云台；因此进入 Track 后必须 REOBSERVE。
- 当前已验证 Track runtime readback 是 `aiGetAiStatusR().ai_main_mode`；mode=2 不等于 follow health 良好。
- 手动 Look 会关闭 AI；恢复跟随必须显式恢复 AI/Track。
- Tail2 已试的 OffsetX/Y、tail-air offset 路径没有可验证构图偏移效果。
- 显式 zoom 有效；TargetZoomType 只视为 hint。
- MVP 媒体 Provider 为 `host_uvc`。
- 无 native candidate list / tracking bbox。

## 3. Runtime 结构

建议保持当前代码可运行，不做一次性大重构：

```text
Caller / Script / future Agent
        ↓
CapabilityRuntime
├─ Capability lifecycle / task / continuation
├─ StateRegistry
├─ ResourceOwnership
└─ Cancellation / deadlines
        ↓
Tail2Adapter
├─ Target / Track
├─ Look
├─ Zoom / Framing hints
└─ Device status
        ↓
native libdev bridge

ObservationService
├─ frame-bound Observation
├─ CandidateProvider
├─ host_uvc photo/record
└─ read-only status page
```

第一步先**包住**现有 `Observer / ObservationService / Bridge`，等正式契约稳定后再移动实现。

## 4. M1A — Runtime contract + state/ownership

交付：

- `CapabilityRequest`：request_id / task_id / capability / args / observation_id / deadline。
- `CapabilityResult`：execution / requested / sdk_reported / visual_check / artifact / errors。
- 生命周期：accepted / running / reobserve_required / completed / constrained / unsupported / failed / cancelled / indeterminate。
- continuation_id：世界变化需要重新观察时继续同一个语义任务。
- StateRegistry：device / observation / target / track / look / framing / media。
- ResourceOwnership：LookOwner、MediaOwner、DeviceWriter。
- 单写者执行队列和 cancel token。
- native bridge 隔离、timeout 后显式重建 session。

**M1A 不改变真机动作策略。** 先把已有动作放到正式边界里。

## 5. M1B — Target + Track 金链

上层调用：

```text
observe.snapshot
→ target.select(candidate_ref)
```

如果设备处于 Normal：

```text
target.select
→ Runtime prepare Track
→ wait ai_main_mode=2
→ REOBSERVE_REQUIRED
→ caller 获取 Observation B
→ 重新 ground 同一语义目标
→ target.select(B)
→ Box
→ verify
```

如果设备已经处于 Track，可直接对当前 frame-bound Observation 下发 Box。

状态必须区分：

- `runtime_mode`: normal / track / unknown
- `ai_requested`: enabled / disabled / unknown
- `follow_health`: unknown / observed_following / degraded

不允许 `runtime_mode=track` 自动推出 `follow_health=observed_following`。

真机回归：双目标 A↔B target-switch。

## 6. M1C — Look + Media

### Look

- Manual Look 先获得 Look ownership 并 disable AI。
- bounded nudge / stop。
- Manual Look 结束不自动恢复用户没有请求的跟踪。
- `track.start` 负责重新 enable AI、恢复必要 runtime state，并在视角变化后要求 REOBSERVE。

### Media

- capture：请求后的新帧 → artifact。
- record：同一 recording_id 贯穿 start/stop。
- UVC reconnect / camera_epoch change：活动 recording 必须 abort 或 finalize，并带 reason；不能跨 epoch 静默拼接。

## 7. M1D — Framing Solver v1

M1 首版只承诺**居中景别**：

- normal
- full_body
- half_body
- close_up

暂不承诺 off-center composition；当前 Adapter capability 明确返回 unsupported / constrained。

执行顺序：

```text
framing intent
→ device framing hint
→ Observe
→ visual scale check
→ 必要时 bounded explicit zoom step
→ Observe
→ complete / constrained
```

要求：

- 每次只做小步；
- 有最大步数、zoom 范围和 deadline；
- zoom readback 标注异步/stale；
- visual_check 必须引用具体 Observation；
- device hint applied ≠ framing visually satisfied。

## 8. M1E — 无模型端到端

至少提供一个确定性脚本，不包含 SDK 名：

```text
Observe
→ Select concrete target
→ REOBSERVE if needed
→ Track
→ Framing
→ Capture
→ Stop / Result
```

状态页必须能看到：

```text
Capability
→ Adapter action
→ SDK result
→ Device state
→ Observation verify
→ Artifact
```

M1 完成后，这个脚本的每一个调用都能直接变成 M2 Agent tool，而不用改设备层。

## 9. Gate

### M1A Gate
- formal request/result contract；
- single writer；
- cancel/indeterminate；
- state registry；
- 不影响现有 M0/M0.5 测试。

### M1B Gate
- 两目标切换可重复；
- Normal→Track 的 REOBSERVE 纪律由 Runtime 强制；
- 上层不接触 SDK。

### M1C Gate
- Manual Look ownership 正确；
- 显式 Track 恢复；
- recording 不跨 epoch。

### M1D Gate
- 至少一种 centered framing 有闭环；
- 不可实现的 offset 不伪造成支持。

### M1 Exit
- 无模型脚本完成 Target→Track→Framing→Capture；
- cancel/stop 可解释；
- trace 可定位错误层；
- 文档与状态页只描述当前能力，不暴露内部试错历史。

## 10. 非目标

M1 不做多模态模型、Application/App Store、人格记忆、多 Agent、MCP、device-native media 下载、native candidate 逆向或大范围 SDK 探索。
