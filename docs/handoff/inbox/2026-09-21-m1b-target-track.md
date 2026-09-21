# M1B 报告：Target + Track 金链（离线完成，真机待跑）

日期：2026-09-21
分支：`local/m1b-target-track`
基线：`130ede955fe301de1c21ae1ac452a9777b402880`（`m1/capability-runtime`）
阶段：M1B（Issue #11）

本轮先完成代码与离线测试，**设备未开**。真机按 B0→B6 待 exact-head 确认后执行。

## 代码

- `tail2_mvp/adapter.py`
  - Track state model：`track.status` 返回 `runtime_mode / ai_requested / follow_health / ai_main_mode_raw / source / stale`。规则：`ai_main_mode==2` 只置 `runtime_mode=track`；**绝不**据此置 `follow_health=observed_following`（默认 unknown）。
  - `target.select`：first-class `request.observation_id` 为准；先 `Observer.check_observation`（frame/epoch/freshness/calibration，**无设备调用**），未处于 Track 时先 `track.enter`（自动确保 AI enabled）→ 返回 `REOBSERVE_REQUIRED` + continuation payload `{reason:"track_runtime_entered", target_ref, previous_observation_id, required_next:"reobserve_and_reground"}`；旧 bbox 不会被 Box。
  - `track.start`：显式确保 AI enabled → `track.enter` → 视角变化则 `REOBSERVE_REQUIRED`；`follow_health` 归零 unknown。
  - `track.verify_follow`：在 Track 内采样 yaw，达到阈值且无丢失才置 `follow_health=observed_following`；否则 unknown/degraded（有 `visual_check`）。
  - stale/epoch/calibration 失效的 observation 一律 `REOBSERVE_REQUIRED` 且**零设备写**。
- `tail2_mvp/observer.py`
  - `check_observation()`（无设备校验）；`invalidate(reason)`（清 ObservationStore/calibration/selected/ROI/track/framing）；`track.enter` 支持 `selection`+`class` 并先确保 AI enabled；`handle(request, *, timeout)` 把 cooperative deadline 传到 bridge；补 `position.list/recall` dispatch。
  - `handle` 返回**裸结果**（协议信封只在 CLI `_execute` 层）。
- `tail2_mvp/harness.py` + `run_capability`
  - 最小真实组装：`CapabilityRuntime → Tail2Adapter → Observer → RuntimeSession → bridge`；`RuntimeSession.on_rebuild(epoch) → Observer.invalidate`；rebuild 后 Observer 走 `session.request`（自动用新 bridge）。
  - CLI：`python -m tail2_mvp capability --bridge ... --backend dshow --device-name 'OBSBOT Tail 2 Camera' ...`，stdin 读 `{capability, args, observation_id, deadline_s, task_id}`，输出 `CapabilityResult`。**调用侧不出现 SDK 名。**
- `tail2_mvp/runtime.py`：`ReobserveRequired` 统一（`observations` 复用），带 continuation payload；task 级 cancel 已在前一轮完成。

## 测试

- 新增/更新 `tests/test_adapter.py`（Target/Track/continuation/stale-zero-write/track.status/follow verify/task cancel/harness assembly+rebuild）。
- **108/108 通过**（Windows x64 + Linux，含 6 native）。
- 覆盖 M1B 离线要点：Normal→prepare→REOBSERVE；Track 内 Box；stale 零设备写；mode=2 不置 following；follow verify 证据分层；session rebuild 失效并强制重观察。

## 待跑真机（B0→B6）

`B0` 只读绑定/校准/状态；`B1` Normal→target.select→REOBSERVE；`B2` continuation→新 Observation→Box A→视觉/yaw 证据→follow_health；`B3` A↔B 切换；`B4` stale 零设备写；`B5` cancel（fake/slow bridge 主验证）；`B6` bridge rebuild 失效（host/fake path）。证据按 Issue #11 格式记录。
