# M0.5 窄实验：ai.control 两态 diff 与四条 Target/Track 序列（脱敏）

日期：2026-09-20
分支：`local/m0-5-state-dump`
基线：`1d603482e7cab9cdf4812632b34ae92f8bbb6235`（= PR #6 merge `3609199` + handoff 文档）
设备：Tail2（alias `Tail2-A`），固件 `7.2.9.41`

只读 dump 与序列原始 JSON 留本地 `.local/dump/`、`.local/seq/`。

## 1. ai.control 0–23：Normal vs 手势 Track

方法：设备分别处于 Normal 与手势 Track，`ai.control.get`（Human target_type=0，文档化类型）逐项读取；Track 态复跑一次以排除瞬时读错误。

**结果：`ai_main_mode` 0（Normal）↔ 2（Track），但 `DevControlParaType` 0–23 参数 0/24 变化。**

| para | name | kind | Normal | Track |
|---|---|---|---|---|
| 0 | motion | bool | false | false |
| 1 | fore_track | bool | false | false |
| 2 | composition | bool | false | false |
| 3 | tracker_type | int | 0 | 0 |
| 4 | gim_ctrl_mode | int | 0 | 0 |
| 5 | gim_ctrl_speed_mode | int | 3 | 3 |
| 6 | pan_gain_adaptive | bool | false | false |
| 7 | pan_gain_value | float | 0.5 | 0.5 |
| 8 | pan_locked | bool | false | false |
| 9 | pitch_gain_adaptive | bool | false | false |
| 10 | pitch_gain_value | float | 0.5 | 0.5 |
| 11 | pitch_locked | bool | false | false |
| 12 | auto_zoom_customized | int | 1 | 1 |
| 13 | auto_zoom_mode | int | 0 | 0 |
| 14 | offset_adaptive_x | bool | false | false |
| 15 | offset_x | float | 0.0 | 0.0 |
| 16 | offset_adaptive_y | bool | false | false |
| 17 | offset_y | float | 0.0 | 0.0 |
| 18 | limit_auto_selection | bool | false | false |
| 19 | limit_pan_min | float | -100.0 | -100.0 |
| 20 | limit_pan_max | float | 100.0 | 100.0 |
| 21 | limit_pitch_min | float | -30.0 | -30.0 |
| 22 | limit_pitch_max | float | 30.0 | 30.0 |
| 23 | auto_zoom_speed | int | 1 | 1 |

**结论**：设备端“跟踪开关”是**设备级状态，不暴露在任何 AI 控制参数里**；唯一可观测点是 `aiGetAiStatusR().ai_main_mode`（0↔2，sub_mode 恒 0）。`aiSetAiTrackModeEnabledR` / legacy `aiSetEnabledR` 均不改变它。→ M1 的 `Track` 原语必须以 `aiGetAiStatusR`（或设备事件）为准，不能读控制参数。

其余两态共用基线：速度档 3（Fast）、增益 0.5、auto_zoom_customized=1、auto_zoom_mode=0、auto_zoom_speed=1、pan 限 ±100、pitch 限 ±30、各锁/偏移关。

## 2. 四条窄序列（五类证据）

统一证据：SDK rc / `ai_main_mode`+sub / 云台 yaw·pitch / 视觉 / zoom。采样 10s，操作者在选择后左右走动。zoom 全程 1.0（无自动变焦变化）。

### A. Normal → Box
- `ai_main_mode` 起始/结束：0 / 0；Box 下发 rc=0（requested ROI 已发）。
- 云台：yaw 恒 −0.93，pitch 恒 −22.45（**不跟随**）。
- 结论：**Normal 下 Box 不会启动跟踪**。

### B. Normal → Center → Box ✅
- `Center`（带 observation_id）rc=0 → `ai_main_mode` 0→**2**，yaw −0.93→−6.75（开始接管）。
- 随后 `Box(具体人)` rc=0。
- 采样 yaw：8.31 → −1.31 → −12.85 → −18.82 → −4.22 → 9.19 → 0.22 → −16.72 → −20.18 → −2.95（**持续跟随**）；pitch 同步变化；操作者目视确认“在跟踪”。
- 截图：`.local/service/seq_B_end.png`（人被重新构图，requested ROI 在脸上）。

### C. Normal → Largest → Box ✅
- `Largest` rc=0 → `ai_main_mode` 0→**2**，yaw 8.26→5.25。
- `Box` 后 yaw：−8.44 → 11.83 → −6.06 → −23.09 → −3.38（跟随）。

### D. 手势 Track → Box ✅
- 起始 `ai_main_mode`=2（设备手势开启）。
- `Box` rc=0 后 yaw：−19.94 → −23.64 → 4.73 → −21.55 → 5.41（跟随）。

## 3. 结论（供 M1 Track/Target 原语）

1. **`target.select(Box)` 单独不启动跟踪**（Normal 下 rc=0 但 mode 恒 0）。
2. **Track 运行时入口有两个**：设备端手势，或 `aiSetSelectedTargetR(Center/Largest)`。二者都把 `ai_main_mode` 置 2。
3. **指定具体对象需要先处于 Track，再用 Box**：即 Tail2 的真实模型是
   `进入 Track 运行时 → Box 选择具体目标 → 持续跟随`。
4. M1 建议：
   - `track.start()`/`target.select()` 在 Adapter 内归一化为“确保 Track（读 `aiGetAiStatusR`，必要时用 Center/Largest 或设备手势）+ Box 具体目标”；
   - 产品语义仍保持 Target/Track 分开，把该副作用写入 `sdk_reported.side_effects`；
   - `Track` 状态只信 `aiGetAiStatusR`。
5. 设备在一次服务结束后会自动回到 Normal（操作者观察），即 **Track 状态不跨会话稳定保持**，不能假设复用。

## 4. 真实几何标定（identity，已验证）

按 review 约束把标定验收升级为**从样本自动推导镜像/旋转并强制单调**（`CalibrationStore.verify`），随后做真机 6 点采样（操作者按**图像坐标**就位，避免左右主观参照）：

| 样本 | 图像 x | 图像 y |
|---|---|---|
| left | 0.169 | 0.479 |
| center | 0.487 | 0.449 |
| right | 0.817 | 0.506 |
| top | 0.491 | 0.175 |
| middle | 0.510 | 0.476 |
| bottom | 0.501 | 0.811 |

- 横向 left<center<right → **mirror_x=false**；纵向 top<middle<bottom → **rotation_deg=0**；crop=null，zoom=1.0。
- 结论：**UVC 归一化坐标与 Tail2 SDK ROI 同向同原点（identity）**。
- 结合 Sequence B（Box 在该标定下跟对目标），ROI 坐标契约这次是**真实标定 + SDK 选中结果**，不再是自证。
- profile 持久化于 `.local/service/calibration/tail2-A-640x480.json`（本地）。

验收规则（已实现）：`calibration.profile` 永远 `verified=false`；`verify` 只有在六点齐全、且横向/纵向都单调（分离 >0.05）时才置真，并据样本推导 mirror/rotation；`camera_epoch` 变化即失效。

## 5. 注意与待收紧

- 快照帧上的 face 检测**偶发为空**（后台检测器有、同步快照帧没有），本轮空候选时使用 **agent_box fallback**。
- 状态页 `preview`+`overlay` 仍只是展示，不作为正式 Agent Observation（正式走 frame-bound Observation 原子对象）。
- `host_uvc` recording 跨 UVC reconnect 的 abort/finalize + epoch reason 仍未补。
- 本次几何标定为 640×480、1x、横向模式；**镜像/竖屏/裁切/变焦变化后需重新标定**（当前实现靠 `camera_epoch` 与 profile 变更失效，尚未覆盖手持重装等未上报变化）。
