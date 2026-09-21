# SDK Sweep B 报告：behavioral carry-over + Gesture / IQ / Preset·Boot / Status

日期：2026-09-21
分支：`feature/sdk-sweep-b`
基线：`main @ 84607df1a7fb6412e710a103244bb859d0843b7e`
设备：Tail2，固件 7.2.9.41，UVC；真实日志/图像在 `.local/sdk-sweep/`。
本轮**未新增正式 Primitive API**（只加 probe op 与实验脚本）。

统一证据框架：`Request → SDK acceptance → Expected Effect Predicate → Evidence → Verdict`，
输出 `accepted / effect_observed / no_effect_observed / evidence_insufficient` 再映射 Truth Map 状态。

## 0. 结论摘要

- **B0 拿到了两个硬结论**：`PanLocked` / `PitchLocked` 的行为谓词成立（各 2 次重复）。
- **B2 拿到一个视觉硬结论**：`cameraSetWhiteBalanceR` 有强视觉效果（Tungsten → 整帧蓝偏）。
- **B3 拿到一个硬结论**：`aiTrgGimbalBootPosR` 精确回到 boot pose。
- **B4 拿到一个架构级否定结论**：`FastDevStatusCallback` 在 Tail2 上从不触发。
- 其余高价值项按纪律记 `evidence_insufficient`，并写明原因（不是猜 no-op）。

## 1. B0 behavioral carry-over

### 1.1 有效的行为谓词（VERIFIED）

方法：absolute reset 到 0/0（已验证）→ 单次 `target.select` box → 2.8s 后读 attitude →
再次 absolute reset。**每个 Track 会话只发一次 select**，两次测量之间必复位，避免累积漂移。
两台固定 Tiny 作为 A/B 目标（左下/右下）。

| 条件 | rep1 yaw_span | rep2 yaw_span | rep1 pitch_span | rep2 pitch_span | verdict |
|---|---|---|---|---|---|
| baseline | 21.63 | 19.09 | 11.24 | 12.39 | 参考 |
| `PanLocked=true` | **0.00** | **0.00** | 1.22 | 1.92 | **VERIFIED**（pan 响应被抑制，pitch 仍动） |
| `PitchLocked=true` | 20.01 | 42.85 | **0.00** | **0.00** | **VERIFIED**（pitch 响应被抑制，yaw 仍动） |

机制澄清（重要）：这两轮里 `ai_main_mode` 始终为 **0** —— 即 **Normal 模式下的 Box 选择是一次性
reframe，不进入 Track**；`PanLocked/PitchLocked` 直接按轴门控这次 reframe。这修正了“Normal Box
完全不动作”的粗说法：它不跟踪，但会 reframe。

### 1.2 证据不足（evidence_insufficient，附原因）

- `GimCtrlSpeedMode` 4 vs 3：settled 位置无差异（20.11 vs 21.63）——**settled-position 谓词看不见速度**，
  需要时间序列/瞬态谓词。
- `TrackerType=LimitArea` + Pan ±15：LEFT 14.9 / RIGHT −4.92，未观察到超出自然范围的钳制。
- `Motion / ForeTrack / Composition / Pan·PitchGainAdaptive·Value / AutoZoomCustomized·Mode·Speed`：
  缺少可靠的运动源与判据（Composition 需要 frame-bound bbox 指标；ForeTrack 需要遮挡场景）。
- **谓词设计本身的否定**：Track（mode 2）下用原生速度从外部扰动云台，**被 AI 吸收**
  （`push_delta ≈ 0`，6 次试验）⇒ “外部扰动 + 观察回拉”这一类锁测试在 Tail2 上不可用。

## 2. B1 Gesture / Gesture Tracking

**配置可写性（全部 OK）**：`aiSetGestureParaR` / `aiGetGestureParaR`、`aiSetGestureTrackParaR` /
`aiGetGestureTrackParaR` 均有 **tail2** 重载，全部 writable + readback + 已还原。

默认值（Tail2 出厂/当前）：

| 项 | 值 |
|---|---|
| Gesture / TargetSelection / Zoom / Record / Snapshot / Rolling | **true** |
| DynamicZoom / Mirror | false |
| ZoomFactor | 1.0（float） |
| GestureTrack PanMin/Max | −45 / +45 |
| GestureTrack PitchMin/Max | −30 / +30 |
| HandType | 0（Right） |
| TrackSpeed | 5（int） |
| PanEnabled / PitchEnabled | true / true |
| RestSeconds | 3 |

**Ownership 冲突**：本轮未取得真机手势，**未测** ⇒ `evidence_insufficient`。
但已确认一个产品事实：**手势默认全开**，因此它是与 Agent 并行的活跃 Intent Source，Runtime 必须
显式仲裁（这与 Issue #17 的预期一致）。
只读采样显示手势参数读写**不改变** `ai_main_mode / ai_sub_mode`（配置面与运行态分离）。

## 3. B2 Focus / IQ

| 项 | 结果 | verdict |
|---|---|---|
| `cameraGet/SetAutoFocusModeR` | 1(AFC)→2(AFS)→回读→还原 1 | READBACK / writable |
| `cameraGet/SetAFCTrackModeR` | 3(Foreground)→1(Face)→回读→还原 3 | READBACK / writable |
| `cameraGetFocusAbsolute` | rc=0，focus=0，auto_focus=true | READBACK_VERIFIED |
| `cameraGet/SetWhiteBalanceR` | 0(Auto,5300K)→3(Tungsten)→回读→还原 | **VERIFIED**（视觉：整帧强烈蓝偏） |
| `cameraGetRangeWhiteBalanceR` | rc=0，返回 range | READBACK_VERIFIED |
| `cameraGet/SetWdrR` | 0→1→回读 1；还原 0 时**回读滞后数秒** | write=async，READBACK 有时序陷阱 |

对原语层的影响：焦点/白平衡是**可靠的相机状态**（有 getter + 视觉），适合未来做 Camera policy；
但 WDR 是异步的，任何“写入后立即判定”的逻辑都会误判。`cameraSetFaceFocusR`、`cameraSetExposureModeR`、
`cameraSetPAEEvBiasR` 已在 probe 中但未逐项闭环（`evidence_insufficient`）。

## 4. B3 Preset / Boot / Gimbal config

| 项 | 结果 | verdict |
|---|---|---|
| `aiGetGimbalPresetListR` | len=0（无预置） | READBACK_VERIFIED |
| `aiGetGimbalBootPosR` | id 0、roll/pitch/yaw 0、zoom 1.0 | READBACK_VERIFIED |
| `aiTrgGimbalBootPosR` | 先 yaw10/pitch5 → 触发后**精确 0/0** | **VERIFIED** |
| `aiSetGimbalParaR` PanReverse(bool) | false→true→false，回读一致 | writable + READBACK |
| `aiSetGimbalParaR` limits | −100/100→−120/120→回读一致，已还原 | writable + READBACK |
| `aiSetGimbalParaR` PresetSpeed | 1.0→2.0 **回读仍 1.0**；1.0→0.5 回读 0.5 | **CONSTRAINED**（2.0 超范围被忽略） |
| limits 的实际作用 | PitchMax=5 后命令 pitch=20 → **仍到 20** | 限位**不约束 absolute Look**（可能只约束 Track 范围） |
| persistent boot set / factory reset | 未执行 | `DEFERRED_UNSAFE` |

## 5. B4 Status / Callback / Lifecycle

| 项 | 结果 | verdict |
|---|---|---|
| `nextRefreshDevStatus` / `fastNextRefreshDevStatus` | rc=0，可调用 | accepted |
| `DevStatusCallback` | 触发后 **~2s 一次**，10 次计数，`age_s` 0.5–2s | **VERIFIED**（事件驱动可用） |
| `FastDevStatusCallback` | **50s+ 内 0 次**（含 fast refresh 请求） | **UNSUPPORTED_TAIL2**（Tail2 不投递） |
| `cameraStatus()` | 可调用，返回 union；**未解析**（布局无文档） | accepted，`NO_PUBLIC_PATH`（payload 契约） |
| `setDevChangedCallback` | 已注册，1 次初始事件；未热插拔 | accepted，`evidence_insufficient` |

对 Runtime 的影响：**状态轮询可以部分换事件**（普通 DevStatusCallback 可靠），但 **fast 路径不可用**，
所以仍需保留 polling 兜底。hotplug 是否能可靠驱动 `camera_epoch bump / invalidation` 未验证。

## 6. LimitedZoneTrack（sample 新发现家族，高优先队列）

6 个 getter（Enabled / AutoSelect / YawMin·Max / PitchMin·Max）**全部 rc=−1**；`aiSetLimitedZoneTrackEnabledR`
返回 rc=0 但无任何回读，也无可见效果 ⇒ `evidence_insufficient`（倾向 `UNSUPPORTED_TAIL2`）。
`aiSetZoneTrackStateR` / `aiSetZoneTrackGimbalEnabledR` / `aiSetTrackingModeR` 已加 probe，未闭环。

## 7. 危险状态与恢复（必须记录）

对 **Common 物体**做 Box 选择后，若该物体离开画面，设备会停在 `ai_main_mode=2 / sub=20(Common)` 并持续
搜索 → 云台一路跑到限位（实测 yaw −135°、pitch 55°；操作者重连相机时表现为**黄灯**）。
恢复路径（已验证）：`target.clear` → `look.stop` → `aiSetGimbalMotorAngleR(0,0)` → 读回 0/0 →
`aiSetEnabledR(true)`。
⇒ 产品含义：**“跟踪一个会离开画面的物体”需要一个 watchdog**（超时/出画即清目标），否则 Agent 会把
云台留在失控态。这条应进入后面的 Runtime 设计。

## 8. 对中间层的输入

1. `PanLocked/PitchLocked` 是**可用的构图稳定原语**（按轴冻结），且有 clean 谓词。
2. `aiTrgGimbalBootPosR` 可作为“回中/回到基线视角”的原语。
3. `cameraSetWhiteBalanceR` 有可靠 getter + 强视觉，是合格的 Camera policy 候选；WDR 因异步需要
   时序谓词。
4. `FastDevStatusCallback` 不可用 ⇒ 事件驱动只能部分替代 polling。
5. 物体跟踪需要 **watchdog**；这是本轮最重要的产品级发现。

## 9. 未做 / 需要下一轮

- 手势所有权（需要真人做手势）。
- Composition / ForeTrack / Gains / AutoZoom 的行为（需要可靠运动源与帧域指标）。
- hotplug / reconnect 的 callback 可靠性。
- `cameraStatus()` union 的 Tail2 布局（需要厂商 payload 契约）。
