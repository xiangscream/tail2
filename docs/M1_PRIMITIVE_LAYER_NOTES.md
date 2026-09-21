# M1 中间原语层：SDK→原语映射与纪律

2026-09-20 · 供 Capability Runtime 实现使用。依据 `docs/Tail2_CAPABILITY_MAP.md`（API 底座）+ M0/M0.5 真机结论。状态：`[V]` 真机证实、`[A]` 仅 SDK 接受、`[U]` 未知。

## 0. 三条总纪律

1. **语义解耦、执行接受现实耦合**：Target（我指谁）/ Track（持续跟谁）/ Framing（构图）在 Runtime 分离；Adapter 记录底层副作用。
2. **证据分层**：`requested / sdk_reported(source+time+stale) / visual_check / artifact` 分开；`rc=0` 只代表接口接受。
3. **一切绑定帧与 epoch**：坐标/候选绑定 `observation_id`（`frame_seq/stream_session/camera_epoch/calibration_id`）；`camera_epoch` 变化即失效重来。

## 1. 原语 → SDK 映射

### Observation（观察）
| 项 | 内容 |
|---|---|
| 实现 | PC 侧 UVC（DirectShow/MSMF）单属主采集；SDK 不取帧 |
| 绑定 | 按设备名 `OBSBOT Tail 2 Camera`（避免 index 漂移）`[V]` |
| 输出 | frame + `observation_id/frame_seq/stream_session/camera_epoch/size/received_mono` + 同帧候选 |
| 纪律 | 同帧候选（`candidate_frame_seq==frame_seq`）；重连 bump `camera_epoch` 并清候选 |
| 关键 | host 收帧时间 ≠ 曝光时间 |

### Target（我指谁）
| 项 | 内容 |
|---|---|
| SDK | `aiSetSelectedTargetR(DevTargetSelection)`（Tail2）`[V]`；`aiDelSelectedTargetR`/`Delete` 清除 |
| 选框 | `Box`（归一化 ROI）、`Center`、`Largest`、`Clicked` |
| 前置 | **必须处于 Track（`ai_main_mode==2`）才能 Box**；否则拒绝并要求 `enter Track → REOBSERVE` |
| 输入 | `observation_id` + `candidate_id`（或合法 bbox）；校验 session/epoch/freshness/calibration/候选归属 |
| 副作用 | `Box` 不置 `ai_main_mode`；`Center/Largest` 置 2 并**会移云台**（进入 Track 时旧 bbox 失效） |
| 结论 | **先进入 Track 运行时（手势或 Center/Largest）→ REOBSERVE → 在具体帧上 Box 目标** |

### Track（持续跟谁）
| 项 | 内容 |
|---|---|
| 进入 | 设备手势，或 `Center/Largest`；`aiSetAiTrackModeEnabledR` 不改 `ai_main_mode`（`[A]` 无效） |
| 恢复 | 手动 Look 后必须 `aiSetEnabledR(true)` **恢复 AI**（见 §2） |
| canonical 回读 | `aiGetAiStatusR().ai_main_mode`（0 Normal / 2 Track）；**`2` ≠ 正在跟随**（`[V]`） |
| 跟随判定 | 只能在目标移动时用 yaw 响应/目标 cx 有界判断；无 native tracking-box 回读 |
| 停止 | **无单条 SDK 退出 Track**；靠设备手势/官方软件/断电，或**重开会话**（会话结束设备回 Normal） |

### Framing（构图）
| 项 | 内容 |
|---|---|
| 产品级 | `aiSetTargetZoomTypeR(full/half/close/normal)` `[A]`：SDK accepted，**视觉变化弱** |
| 底层变焦 | `cameraSetZoomAbsoluteR(1.0~2.0, speed 1~10)` `[V]` 可见；异步、getter 滞后；`cameraGetZoomAbsoluteR`、`cameraGetZoomRangeAbsoluteR` |
| AI 自动变焦 | `aiSetAiAutoZoomR(bool)` `[A]` 弱 |
| 构图参数 | `aiSetControlParaR(DevControlTargetType, DevControlParaType, …)`：Composition/OffsetX/Y/AutoZoomMode/Customized/Speed/PanLocked/PitchLocked（`[U]` 语义/单位未知，实测 OffsetX 无可见效果） |
| 结论 | Framing 是 **Solver**：组合 Track 状态 + auto zoom + 显式 zoom + 构图偏移 + 轴策略 → 视觉验证；不是单一 SDK 包装 |

### Look（视线）
| 项 | 内容 |
|---|---|
| 速度 | `gimbalSpeedCtrlR(pitch,pan,roll)` `[V]`；pan 正→yaw 正；停止后残余≈0.4° |
| 姿态回读 | `gimbalGetAttitudeInfoR(xyz[3])` `[V]` 但**间歇 rc=-1** → last-good+stale |
| **纪律** | 手动控云台前 `aiSetEnabledR(false)`，**结束后必须 `aiSetEnabledR(true)`**；否则“蓝灯不跟随”（`[V]`） |
| 所有权 | 手动 Look 暂停 Track；恢复需显式 `track.start` |

### Capture / Record（媒体）
| 项 | 内容 |
|---|---|
| MVP | **`host_uvc`**：photo 取请求**之后**新帧并持久化；record 写本地文件，stop flush/finalize |
| device-native | `cameraSetMediaOperateParamR(DevMediaStreamId, DevMediaParamOperation)` `[A]`：setter rc=0，但 record 回读恒 Stop、capture getter rc=-1；UVC 与机内录像互斥（手册+操作者）；**文件取回路径未文档化** |
| 结论 | device-native 标 `experimental/unsupported`；不阻塞主链 |

### Position（云台视角预置）
`aiGetGimbalPresetListR` `[V]` len=0；`aiTrgGimbalPresetR(id)` 召回待有 ID；**save 未授权写入**。M1 标 `experimental`。

### Status（聚合状态）
`aiGetAiStatusR`（main/sub mode）、`gimbalGetAttitudeInfoR`、`cameraGetMediaOperateParamR`、`zoom.get`、`cameraStatus()`/回调（2–3s 滞后，union 未解析）。全部 **last-good + source time + stale + unsupported**。

### Stop（停止）
- Track：`aiSetEnabledR(false)` + `gimbalSpeedCtrlR(0,0,0)`（`look.stop`）`[V]`；
- 无独立硬件看门狗；主机超时 ≠ 设备已停；不确定则现场确认；
- 退 Track 只能手势/重开会话。
- `device.stop_all`：cancel 编排 + stop track + 零速 + finalize host_uvc recording。

## 2. 关键副作用与陷阱（务必在 Adapter 归一化）

1. **手动 Look 关 AI**：`gimbalSpeedCtrlR` 前需 `aiSetEnabledR(false)`，**之后必须 `aiSetEnabledR(true)`**；否则后续 `Center` 只置 mode=2 不跟随。
2. **进入 Track 会移云台**：`Center/Largest` 会接管视线 ⇒ Box 前必须 **REOBSERVE**，不能用旧 observation 的 bbox。
3. **`ai_main_mode=2` ≠ 正在跟随**：需“目标移动→yaw 响应”作为跟随证据。
4. **无 native tracking box**：目标“被选中”无法直接回读；页面只画 requested ROI。
5. **`Box` 需要 Track**：Normal 下 Box 被接受但不启动跟踪。
6. **bridge 超时即隔离**：native 单飞 bridge，任一调用超时 → 关闭 → 所有后续失败；Runtime 必须检测并**重开会话**（并重标定/清 ROI）。
7. **设备卡死**：反复混合写后可能“蓝灯不跟随”，需官方软件拖摇杆/断电恢复；M1 需提供“跟随健康检查 + 复位提示”。
8. **gimbal 回读间歇失败**：不能把一次失败当作 0。
9. **发现慢**：`device.list` 有界轮询；重连 bump `camera_epoch`。

## 3. 枚举速查（实现用）

- `AiMainModeType`：Normal=0 / Group / Track=2 / GestureTrack / Desk / WhiteBoard
- `AiTrackSubModeType`：Human{Normal=0,FullBody=1,HalfBody=2,CloseUp=3,CustomAutoZoom=4,Headless,LowerBody}、Animal=10/13、Common=20/23
- `DevTargetSelectionType`：Delete=-1 / Center=0 / Largest=1 / Clicked=2 / Box=3
- `DevTargetClassType`：Ignored=-1 / Human=0 / Animal=1 / Common=2 / HumanOrAnimal=100 / All=101
- `DevTargetZoomType`：Ignored=-1 / Normal=0 / FullBody / HalfBody / CloseUp / Customized / GropHeadless / GropLowerBody / Adaptive=99
- `DevMediaStreamId`：Auto=0/Record/Capture/Live/Rtsp/Ndi/Srt/Uvc/Kcp/Hdmi/Sdi；`DevMediaParamOperation`：Auto=0/Start/Stop/Pause/Resume
- `DevMode`：Uvc=0 / Net=1 / Mtp=2 / Ble=3；`ObsbotProductType`：Tail2=11
- `DevControlParaType` 0–23（见 CAPABILITY_MAP §7）

## 4. 尚未解决 / M1 需回答

- UVC→SDK ROI 映射：**已用双目标 target-switch 验证为 identity**（两个物体同框，Box 谁就切到谁）。单目标不隔离 `Center` 因果。物体“框选+跟踪”=`aiSetSelectedTargetR(Box, class=Common)` 且需先在 Track。
- Framing 的 `aiSetControlParaR`（Offset/AutoZoom/Composition）**语义与单位未知**，实测无可见效果。
- 设备端跟踪开关（手势/App）与 SDK `aiSetEnabledR`/`ai_main_mode` 的完整状态机与“跟随健康”判定。
- 退 Track 的可靠手段（会话重建是否等价于复位）。
- device-native 媒体文件取回路径。
- 原生候选订阅（外部信息任务）。
