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

**结论**：0–23 的结果只支持：**本轮测试的 `DevControlParaType` 里没有 Track 状态差异**。设备端“跟踪开关”未暴露在这组控制参数中；**当前已验证的 canonical readback 是 `aiGetAiStatusR().ai_main_mode`（0↔2，sub_mode 恒 0）**。`aiSetAiTrackModeEnabledR` / legacy `aiSetEnabledR` 均不改变它。事件等其它状态接口未穷尽，不排除存在其它来源。→ M1 的 `Track` 原语以当前已验证的 canonical readback 为准。

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

## 4. 标定：mapping hypothesis + SDK selection outcome（已重做）

**旧逻辑的问题（PR #7 review 指出）**：六个样本的 x/y 都来自 UVC 图、标签也按 UVC 图命名，`left<center<right` 只证明“UVC 自身按标签单调”，天然推出 `mirror_x=false`，没有 SDK 侧观测参与；SDK ROI 若水平镜像，旧代码仍可能给出 identity。已废弃“由 UVC 样本推导 transform”。

**新逻辑（已实现）**：
1. `calibration.profile` 先声明 **hypothesis**（identity / mirror / rotation / crop / zoom），且永远 `verified=false`。
2. `calibration.validate {position}`：确保进入 Track（必要时 `Center/Largest`）→ 等 `ai_main_mode=2` → **REOBSERVE** → 用 hypothesis 计算 ROI → 下发 `Box` → 采样目标位移，返回实际 `uvc_bbox` 与 `sdk_roi`。
3. `calibration.outcome {position, observation_id, uvc_bbox, sdk_roi, selected}`：记录**实际下发 ROI** 与**设备是否选中该位置对应的目标**（视觉/操作者确认）。
4. `calibration.verify`：**六个位置 outcome 全 PASS** 才 `verified`；UVC 六点仅作 geometry sanity（单调检查），**不再决定 mirror/rotation**。
5. `camera_epoch` 变化、profile 变更即失效重标。

**现场几何 sanity（UVC 坐标，保留）**：left(0.169,0.479)、center(0.487,0.449)、right(0.817,0.506)、top(0.491,0.175)、middle(0.510,0.476)、bottom(0.501,0.811)。

**identity hypothesis + SDK 选中结果验证**：本轮尚未逐点下发验证（需现场逐点 Box + 视觉确认），因此当前 `identity` 记为 **STRONG CANDIDATE**，不是 VERIFIED；`calibration.verify` 在跑完六点 SDK outcome 前会拒绝置真。Sequence B 只支持“该场景下 identity 的一次 Box 选对”，不足以单独升级为 VERIFIED。

## 5. M1 Target/Track 流程（必须遵守）

`Center/Largest` 会先接管云台（Sequence B 实测 yaw −0.93→−6.75），进入 Track 前的 Observation bbox 可能失效。Adapter **不得**把 `Center/Largest → Box` 隐藏成无重观察的原子调用。

正确 runtime：

```text
Observation A
  → Agent 想选目标 X
  → 若处于 Normal：enter Track runtime (Center/Largest)
  → 等 ai_main_mode=2 / 视角稳定
  → REOBSERVE (Observation B)
  → 在 B 上重新 ground 同一语义目标 X
  → Box(B)
  → verify follow

若设备已是 Track：直接对当前 frame-bound Observation 下发 Box。
```

探针已据此收紧：`target.select(Box)` 在未处于 Track（`ai_main_mode != 2`）时**直接拒绝**并提示“enter Track → 等 mode=2 → REOBSERVE → Box”；进入 Track 用 `track.enter`。

## 6. 注意与待收紧
- 快照帧上的 face 检测**偶发为空**（后台检测器有、同步快照帧没有），本轮空候选时使用 **agent_box fallback**。
- 状态页 `preview`+`overlay` 仍只是展示，不作为正式 Agent Observation（正式走 frame-bound Observation 原子对象）。
- `host_uvc` recording 跨 UVC reconnect 的 abort/finalize + epoch reason 仍未补。
- 本次几何标定为 640×480、1x、横向模式；**镜像/竖屏/裁切/变焦变化后需重新标定**（当前实现靠 `camera_epoch` 与 profile 变更失效，尚未覆盖手持重装等未上报变化）。

## 7. 跟踪开关：手动 Look 后必须恢复 AI（关键修复）

`dev.hpp` 对 `aiSetEnabledR` 明确写：使用 `aiSetGimbalSpeedCtrlR` 手动控制云台前要**先关 AI**，**控制结束后必须再把 AI 打开**。

- 探针的 `look.stop` / `look.nudge` 只调用了 `aiSetEnabledR(false)`，**从未恢复**；因此每次手动 Look 后设备进入“**蓝灯但 AI 关闭、不跟随**”状态，且 `Center` 只把 `ai_main_mode` 置 2 也不会真正跟随。
- 正确序列（实测）：`aiSetEnabledR(true)` → `Center`（进入 Track，mode=2）→ 目标移动时 **yaw 明显跟随**（-82.34→-88.40→-92.77→-70.59），目标 cx 保持有界（0.35–0.61）⇒ **跟随成立且方向为 identity**。
- 结论：M1 的 `look` 原语在手动动作结束后**必须显式恢复 Track/AI**（`track.start` / `aiSetEnabledR(true)`）；`ai_main_mode=2` 单独不代表正在跟随。

这也解释了本轮之前反复出现的“卡死/不跟随”。
