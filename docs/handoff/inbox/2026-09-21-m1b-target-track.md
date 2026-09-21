# M1B 报告：Target + Track 金链（代码 + 离线 + 真机 B0→B6 完成）

日期：2026-09-21
分支：`local/m1b-target-track`
基线：`130ede955fe301de1c21ae1ac452a9777b402880`（`m1/capability-runtime`）
阶段：M1B（Issue #11）
设备：Tail2（`Tail2-A`，固件 7.2.9.41，VID_3564/PID_FEFC，UVC DirectShow）；真机数据留 `.local/`。

## 结论

- 代码 + 离线测试完成，真机 `B0→B6` 全部执行。
- `B0/B1/B2/B3/B4` 真机 PASS；`B5/B6` 按纪律用 fake/host path PASS。
- M1B 金链 `Observation → semantic target → prepare Track → REOBSERVE → reground → Box → physical response / operator visual confirmation` 在真机走通；`target.select` 在 Track 内切换目标全程 `completed`、**不重进 Track、不 reobserve**。Runtime 不再把单纯 yaw 变化等同于身份级 follow verification。
- 真机暴露 3 条需要定级的限制（见下），建议在进入正式素材库前明确其证据强度与产品含义。

## 代码

- `tail2_mvp/adapter.py`
  - Track state model：`track.status` 返回 `runtime_mode / ai_requested / follow_health / ai_main_mode_raw / source / stale`。`ai_main_mode` 从 `device.status` 读取（旧 `status.ai` 已废弃）。规则：`ai_main_mode==2` 只置 `runtime_mode=track`，**绝不**据此置 `follow_health=observed_following`（默认 unknown）。
  - `target.select`：first-class `request.observation_id` 为准；先 `Observer.check_observation`（frame/epoch/freshness/calibration，**无设备调用**），未处于 Track 时先 `track.enter`（自动确保 AI enabled）→ 返回 `REOBSERVE_REQUIRED` + continuation payload `{reason:"track_runtime_entered", target_ref, previous_observation_id, required_next:"reobserve_and_reground"}`；旧 bbox 不会被 Box。
  - `track.start`：显式确保 AI enabled → `track.enter` → 视角变化则 `REOBSERVE_REQUIRED`；`follow_health` 归零 unknown。
  - `track.motion_evidence`：在 Track 内采样 yaw，只产出 `gimbal_yaw_span` 物理运动证据；**不**把 yaw 变化写成视觉身份验证，`follow_health` 保持 `unknown`，等待后续 frame-bound visual verifier。
  - stale/epoch/calibration 失效的 observation 一律 `REOBSERVE_REQUIRED` 且**零设备写**。
- `tail2_mvp/observer.py`：`check_observation()`（无设备校验）；`invalidate(reason)`；`handle(request, *, timeout)`；`position.list/recall` dispatch；`handle` 返回裸结果。
- `tail2_mvp/harness.py` + `run_capability`：最小真实组装 `CapabilityRuntime → Tail2Adapter → Observer → RuntimeSession → bridge`；`RuntimeSession.on_rebuild(epoch) → Observer.invalidate`；启动时 `CalibrationStore.load()` 载入持久化的 verified profile；CLI `python -m tail2_mvp capability ... --command-file <jsonl>`（调用侧不出现 SDK 名）。
- `tail2_mvp/calibration.py`：新增 `load()`，从持久化设备样本中载入 verified profile（跳过未验证 / `unverified`）。
- `tail2_mvp/__main__.py`：新增 `--command-file`。

## 离线测试

- `tests/test_adapter.py` 覆盖 Normal→prepare→REOBSERVE；Track 内 Box；stale 零设备写；mode=2 不置 following；follow verify 证据分层；task cancel；session rebuild 失效并强制重观察。
- `tests/test_calibration.py` 覆盖 `load()` 持久化 profile。
- Linux 全仓：**103 passed / 6 skipped（native）/ 5 subtests passed**；Windows 侧此前 109/109。

## 真机验证 B0→B6

命令通道：`capability` runtime（`--command-file .local/m1b/cmd.jsonl`，长驻，port 8800 只读页）。

- **B0 PASS（只读绑定/校准/状态）**：`status.get` → `runtime_mode=normal`、`ai_main_mode_raw=0`、`source=sdk`、`stale=false`；`observe.snapshot` frame-bound（`candidate_frame_seq==frame_seq`，含 camera_epoch/stream_session）；calibration 载入 `tail2-A-640x480`（verified、identity、mirror_x=false、rotation 0）。
- **B1 PASS（Normal→prepare Track→REOBSERVE）**：Normal 下 `target.select` → `execution=reobserve_required`、`continuation_id=m1b-task-A`、payload `reason=track_runtime_entered / required_next=reobserve_and_reground`；随后 `track.status` → `runtime_mode=track`、`ai_requested=enabled`、`follow_health=unknown`。
- **B2 PASS（continuation→新 Observation→Box→物理响应）**：新 Observation 后 `target.select(human, bbox 0.30/0.05/0.68/0.78)` → `completed`、`requested_roi_sdk` 与输入一致（calibration verified）、`side_effects=UNVERIFIED`、`follow_health=unknown`；人移动后 `track.motion_evidence {samples:6,min_yaw_deg:0.5}` 记录 `gimbal_response_observed`（yaw_span 15.6°）。操作者现场确认设备在跟随所选目标，但 Runtime 的 `follow_health` **仍保持 unknown**，因为当前没有 native tracking box / frame-bound identity verifier。
- **B3 PASS（A↔B 切换）**：进入 Track 后（`track.start center/human` 建立基线），三种目标切换均 `execution=completed`、**无 reobserve/continuation**，云台产生可测位移：

  | 步骤 | select | Δyaw | Δpitch |
  |---|---|---|---|
  | A 基线（人，画面居中，瓶左/杯右同在框内） | — | yaw −8.07 | pitch 6.83 |
  | A→B | 果茶瓶 `box/common` | +13.5° | +13.4° |
  | B→A | `human` `selection=largest` | −13.3° | −11.9° |
  | A→C | 咖啡杯 `box/common` | −21.0° | +10.7° |
  | C→A | `human` `selection=largest` | +16.5° | −10.4° |

  全程 `track.status.runtime_mode=track`。证据图（`.local/` 本地，未入库）：`b3_scene1 / b3_sw1_B / b3_sw3_A / b3_sw4_C / b3_sw5_A`。
- **B4 PASS（stale 零设备写）**：snapshot 后等 4s（>`max_frame_age_s=2`）再 `target.select` → `execution=reobserve_required`、`error=observation is stale`、`sdk_reported={}`、payload `required_next=reobserve_and_reground`；bridge trace 中 `aiSetSelectedTargetR` 计数不变（零设备写）。
- **B5 PASS（cancel，fake/host path）**：`tests/test_runtime_layer.py` 中 `test_cancel_and_deadline / test_cancel_marks_cancelled / test_cancel_unknown_and_cancel_all / test_deadline_read_only_is_failed / test_deadline_side_effecting_is_indeterminate` 全通过；`tests/test_adapter.py::test_task_cancel_cancels_all_requests_in_task` 通过。
- **B6 PASS（session rebuild 失效，host path）**：`tests/test_adapter.py::test_session_rebuild_invalidates_and_reobserves` 通过（rebuild → `camera_epoch=1` → 旧 observation `target.select` → `REOBSERVE_REQUIRED`）。

## 关键发现 / 限制（建议定级）

1. **human 框选在无人脸/头时静默 no-op。** 框在躯干/手臂/半张脸时 `target.select` 仍返回 `completed` 且 `rc=0`，但云台**零位移**；只有框内存在可检测的人脸/头时才真正动作。运行时当前无法区分“已执行”与“设备忽略”。缓解：A 的回归改用 `selection=largest`（仍属 `target.select`，非 `track.start`），在本轮真机稳定生效。
2. **目标身份由设备 AI 决定，框选不保证身份。** `selection=center/largest` 锁“画面中心/最大的人”；一次相机漂移后 `track.start(center,human)` 实际锁到了**旁边的同事**。无 native candidate list / tracking bbox 可消歧，只能靠“画面内唯一/最大目标”约束，人多了不可靠。
3. **手动 Look 会让云台进入不可控/异常显示态。** `look.stop`（`aiSetEnabledR(false)`）之后 `look.nudge` 仍 `rc=0` 但云台不再动作，设备出现黄→紫状态灯；重新经 `track.start` 启用 AI 后才恢复。另：`look.nudge` 被硬钳在 `±10 dps / ≤500ms`（≈5°/次），而 AI target select 单次可转约 40°。
4. **requested_roi 是“选择帧坐标”语义。** 选择后设备会重新构图，overlay 上固定绘制的 `requested_roi` 会与目标错位（非跟踪框），需要按 `frame_seq` 解释，勿当作实时跟踪框。

## 未做 / 不做

- 本轮不做 Framing / Look / record reconnect / Agent；不含身份级 follow 的量化持续跟踪指标（仅 `track.motion_evidence` 的 yaw span + 操作者现场确认）。
- 未做双人场景下的身份稳定性专项。


## 网页端收口裁决（2026-09-21）

- **M1B PASS**：Target/Track Runtime 金链成立，B0→B6 的目的均满足。
- 不追加“双人身份稳定性专项”作为 M1B blocker。现有结果已经证明 Capability Runtime 的状态转换、REOBSERVE、frame-bound Target、Track 内 target-switch 与 stale 零设备写成立。
- “human 框选静默 no-op / 设备身份不保证”升级为正式产品限制：`target.select completed` 只表示选择请求路径完成，不等于目标身份已确认。
- 在没有 native tracking box / identity readback 的前提下，`follow_health` 不得由 `ai_main_mode` 或 gimbal yaw 自动升级为 `observed_following`。身份级确认留给后续 frame-bound visual verifier（M2/Host Perception）。
