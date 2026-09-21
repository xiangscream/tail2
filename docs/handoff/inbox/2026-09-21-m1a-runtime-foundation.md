# M1A 报告：Capability Runtime foundation（脱敏）

日期：2026-09-21
分支：`local/m1a-runtime-foundation`
基线：`44922904bad65475be42a682df09692b37cc897d`（`m1/capability-runtime`）
阶段：M1A（Issue #8）

离线开发，未操作真机；未改变任何设备动作策略。

## 交付

- `tail2_mvp/runtime.py`
  - `CapabilityRequest`（request_id/task_id/capability/args/observation_id/deadline_s/caller，自动补 id 并校验）。
  - `CapabilityResult`（`execution / requested / sdk_reported / visual_check / artifact / errors / continuation_id / payload`）。
  - 生命周期 `Execution`：accepted/running/**reobserve_required**/completed/constrained/unsupported/failed/cancelled/**indeterminate**。
  - `REOBSERVE_REQUIRED` 作为**续接**（`ReobserveRequired` → `continuation_id`），不是失败。
  - `StateRegistry`：last-good + source + source_mono + age + `stale`/`unsupported`/`error`，`clear(*keys)`。
  - `ResourceOwnership`：`device_writer`/`look`/`media` 等，busy 拒绝、按 owner 释放、`clear`。
  - `SingleWriter`：串行执行；`CancelToken`；`Deadline`。
  - `CapabilityRuntime`：register/execute/cancel/cancel_all；按 capability 声明资源；副作用类超时→`indeterminate`，只读类→`failed`；明确拒绝（`CapabilityRejected`）→`failed`；`UnsupportedCapability`/`Constrained` 分别返回对应 execution。
- `tail2_mvp/session.py`
  - `RuntimeSession`：包装 bridge 工厂；`BridgeError`（超时/退出）触发**显式重建**，bump `camera_epoch`、`rebuilds`，清 epoch 绑定状态（observation/target/track/framing/look/media/orientation）与全部资源所有权；`on_rebuild(epoch)` 回调。
- `tail2_mvp/adapter.py`
  - 薄 `Tail2Adapter`：把产品 capability 映射到现有 `Observer.handle`，产出 evidence；把“未处于 Track / 需重观察”翻译为 `ReobserveRequired`；`track.start` 进入 Track 后返回 `REOBSERVE_REQUIRED`；`framing.set` 只接受 centered scale（normal/full_body/half_body/close_up），其它 → `unsupported`（不伪造 offset）；`record.stop` 未 finalize → `indeterminate`。
  - `observe.snapshot`/`candidates`/`target.*`/`track.*`/`framing.*`/`look.*`/`capture.photo`/`record.*`/`position.*`/`status.get`/`task.cancel` 注册到 runtime。
- 测试：`tests/test_runtime_layer.py`（18）、`tests/test_adapter.py`（10）。

## 结果

- **104/104 通过**（Windows x64 与 Linux；含 6 项 native）。现有 M0/M0.5 测试全部保持通过，未大爆炸重构。
- 覆盖：契约校验、证据分离、单写者串行、资源 busy、cancel、deadline（副作用 indeterminate / 只读 failed）、REOBSERVE 续接、unsupported/constrained、session 重建清状态/资源并 bump epoch、adapter 的 REOBSERVE/证据/artifact 语义。

## 说明 / 边界

- 未接模型；未在脚本中暴露 SDK 名。
- `payload` 承载 capability 专属数据（观察、候选、target），与 `sdk_reported` 分开。
- M1A 不含 Target/Track 金链、Framing Solver、Look/Media ownership 真机策略（分别 M1B/M1C/M1D）。
- 真机回归留待 M1B（由网页端给 exact-head 实验矩阵）。

## PR #10 review 修复（4 个 contract blocker）

1. **task cancel 变为真实取消**：`CapabilityRuntime` 改为 `task_id -> list[token]`（request_id 仍单独索引）；`cancel(task_id)` 取消该 task 全部 active/queued request；`task.cancel` capability 由 Runtime 原生处理，返回 `cancelled_count` 与 `target_task_id`。测试覆盖同一 task 多 token。
2. **observation_id 接进正式契约**：Adapter 以 `request.observation_id` 为准并注入设备调用；若 `args.observation_id` 与之不一致 → 拒绝（`CapabilityRejected`→failed）。上层只用 formal field。
3. **deadline 改为 cooperative 并接通底层**：Adapter 每个调用前检查 token/deadline，并把 `deadline.remaining()`（clamp 0.05–60s）经 `Observer.handle(timeout=...)` 传到底层 bridge；bridge 超时 → `BridgeError` → 隔离并**重建 session**；Runtime 在 handler 返回后若 deadline 已过且为副作用类 → `indeterminate`。**明确不是硬中断保证**（同步 SDK call 无法强杀）。
4. **rebuild 真正失效 Observer 权威状态**：`RuntimeSession.on_rebuild(epoch)` 接到 `Observer.invalidate(reason)`，清 `ObservationStore`、失效 calibration、清 selected/requested ROI/track/framing；旧 observation 一律 `REOBSERVE_REQUIRED`。补**集成测试**（真实 ObservationStore + CalibrationStore + Observer，非 fake StateRegistry）。

测试：**109/109 通过**（Windows x64 + Linux，含 6 native）。
