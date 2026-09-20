# Tail2 SDK 能力底座（M1 原语层输入）

2026-09-20 · 供 M1 设计能力原语与 Provider。基于本地 `libdev_v2.1.0_8`（`include/dev/dev.hpp` SHA256 `d6f12cd9…f74f2d`）静态通读 + M0/M0.5 真机结果。厂商头文件/库不入库。

**状态图例**：`[V]` 真机已证实（有视觉/行为/回读证据）；`[A]` SDK 接受（rc=0）但未证实行为；`[U]` 未测/未知；`[X]` 无接口或不适用。

## 0. 顶层结构

| 类/文件 | 作用 |
|---|---|
| `class Devices`（devs.hpp） | 全局设备管理：`getDevList/getDevBySn/getDevByName/getDevByUuid`、`setDevChangedCallback`（插拔热插拔）、`setEnableMdnsScan`、`close` |
| `class Device`（dev.hpp） | 单设备：`productType/devSn/devName/devVersion/devMode/videoDevPath/videoFriendlyName`；全部能力方法 |
| `dev_set_log_handler`（comm.hpp） | SDK 日志回调（本地 stderr），库版本 1.3.0 |
| `ObsbotProductType` | Tail2=11、Tail2S=16 |
| `Device::DevMode` | Uvc=0 / Net=1 / Mtp=2 / Ble=3 |

设备发现：SDK 异步检测，`device.list` 需**有界轮询**而非固定 sleep（M0 实测 3s 偶发空、8s 稳定）。

## 1. 观察（Observation）

| 能力 | API | 状态 |
|---|---|---|
| UVC 设备路径/名称 | `Device::videoDevPath()/videoFriendlyName()/uvcVersion()` | `[V]` 名称 `OBSBOT Tail 2 Camera`，用于与 DirectShow 绑定 |
| 主机图像 | 由 UVC（DirectShow/MSMF）在 PC 侧采集，SDK 不提供取帧 | `[V]` 单属主采集 640×480 |
| 状态回读 | `cameraStatus()`（2~3s 缓存滞后）、`DevStatusCallback`/`FastDevStatusCallback` | `[A]` 回调仅计数，union 未解析 |
| 强制刷新 | `nextRefreshDevStatus()/fastNextRefreshDevStatus()` | `[U]` |

## 2. Target 与 Tracking

| 能力 | API | 状态 |
|---|---|---|
| 统一选框 | `aiSetSelectedTargetR(DevTargetSelection)`（Tail2） | `[V]` Box/Center/Largest/Clicked 均 rc=0 |
| 选框类型 | `DevTargetSelectionType{Delete=-1,Center=0,Largest,Clicked,Box}` | — |
| 类别 | `DevTargetClassType{Human,Animal,Common,HumanOrAnimal,All}` | — |
| 目标清除 | `aiDelSelectedTargetR` / `DevTargetSelectionTypeDelete` | `[V]` rc=0 |
| 删除目标（旧） | `aiDelSelectedTargetR` | `[U]` |
| 点选/最大/居中 | `aiSetSelectTargetByBox` / `aiSetSelectBiggestTarget` / `aiSetSelectCentralTarget`（tail air） | `[A]` rc=0（biggest/central） |
| 跟踪开关（Tail2） | `aiSetAiTrackModeEnabledR(AiTrackModeType,bool)` | `[A]` rc=0，**未改变 `ai_main_mode`** |
| 跟踪开关（legacy） | `aiSetEnabledR(bool)` | `[A]` rc=0，未改变 `ai_main_mode` |
| 跟踪速度 | `aiSetTrackSpeedTypeR(AiTrackSpeedType)`（tail air） | `[U]` |
| 选区跟踪 | `aiSetZoneTrackStateR` / `aiSetLimitedZoneTrack*`（tiny2/tail air） | `[U]` |
| `DevTargetZoomType` | Ignored/Normal/FullBody/HalfBody/CloseUp/Customized/GropHeadless/GropLowerBody/Adaptive | — |
| `DevTargetViewType` | Ignored/Manual/Full/FullBody/HalfBody/ClassUp/Headless/LowerBody/TargetAuto/NotTargetAuto/Group/Trace | `[U]` |
| `AiMainModeType` | Normal=0/Group/Track/GestureTrack/Desk/WhiteBoard | `[V]` `aiGetAiStatusR` 可读 |
| `AiTrackSubModeType` | Human{Normal=0,FullBody,HalfBody,CloseUp,CustomAutoZoom,Headless,LowerBody}、Animal=10/13、Common=20/23 | `[V]` 可读 |

**关键真机结论**：
- `target.select(Box)` 被接受但 **`ai_main_mode` 保持 0**；`selection=Center/Largest` 会把 `ai_main_mode` 置 **2（Track）**。
- **无 native tracking box 回读**：SDK 不返回设备实际跟踪框。
- 主动跟随：**在设备端跟踪开关已开（手势蓝灯）时可行**（UVC 下 yaw 随人走动变化）；SDK 侧单独 `target.select`/`aiSetAiTrackModeEnabledR` 未必启动跟随。跟踪启动的主责可能在设备端状态，需在 M1 明确“设备跟踪是否开启”的读法。
- HOG 对侧脸/半身不稳；face 台架在正面时可靠（仅台架，不是产品级 detector）。

## 3. Framing 与 Zoom

| 能力 | API | 状态 |
|---|---|---|
| 景别（产品级） | `aiSetTargetZoomTypeR(DevTargetZoomType, DevCustomizedZoomType)`（Tail2） | `[A]` close/half/full/normal 均 rc=0，但**视觉景别变化很弱/无** |
| 视图类型 | `aiSetTargetViewTypeR(DevTargetViewType)`（Tail2） | `[U]` |
| AI 自动变焦开关 | `aiSetAiAutoZoomR(bool)`（tiny2/tail air） | `[A]` rc=0，未证实 |
| 显式变焦 | `cameraSetZoomAbsoluteR(float 1.0~2.0, int speed 1~10)` | `[V]` **真机有效**：face h 0.34→0.82；异步，getter 滞后 |
| 变焦回读 | `cameraGetZoomAbsoluteR(float&)` | `[V]` 归一化值 1.0+ |
| 变焦范围 | `cameraGetRangeZoomAbsoluteR(UvcParamRange&)` | `[V]` `{0,100,1,0,valid}` |
| 相对变焦/停 | `cameraSetZoomWithSpeedRelativeR` / `cameraSetZoomStopR` | `[U]` |
| 数字变焦开关 | `ZoomParamType{PROTOCOL_SET_MANUAL_ZOOM_SPD, PROTOCOL_SET_ENABLE_DIGITAL_ZOOM}` | `[U]` |
| 构图参数 | `aiSetControlParaR(DevControlTargetType, DevControlParaType, …)`（Tail2） | `[U]`（见 §7，M1 重点） |

## 4. Gimbal / Look

| 能力 | API | 状态 |
|---|---|---|
| 速度控制 | `gimbalSpeedCtrlR(pitch,pan,roll)`（legacy） | `[V]` 有效；pan 正→yaw 正；停止后残余≈0.4° |
| 姿态回读 | `gimbalGetAttitudeInfoR(float xyz[3])`（legacy） | `[V]` 但**间歇 rc=-1**（需 last-good+stale） |
| 角度控制 | `aiSetGimbalMotorAngleR(pitch,yaw,roll=-1000)`（形参为 pitch,yaw,roll） | `[U]` |
| 速度（AI 路径） | `aiSetGimbalSpeedCtrlR(pitch,pan,roll)` / `aiSetGimbalStop()` | `[U]` |
| 初始位 | `aiSetGimbalBootPosR/aiGetGimbalBootPosR/aiTrgGimbalBootPosR/aiRstGimbalBootPosR` | `[U]` |
| 云台参数 | `aiSetGimbalParaR/aiGetGimbalParaR(DevGimbalParaType,…)`（Tail2） | `[U]` 见 §8 |
| 视角反向 | `aiSetGimbalYawDirReverseR` | `[U]` |

## 5. Presets（云台视角，非空间位置）

| 能力 | API | 状态 |
|---|---|---|
| 列表 | `aiGetGimbalPresetListR(DevDataArray*)` | `[V]` rc=0、**len=0（当前无预置）** |
| 详情/名称 | `aiGetGimbalPresetInfoWithIdR` / `aiGetGimbalPresetNameWithIdR` | `[U]` 无 ID 可测 |
| 召回 | `aiTrgGimbalPresetR(id)` | `[U]` 无 ID 可测；`position.save` 仍拒绝写入 |
| 增删改 | `aiAddGimbalPresetR/aiDelGimbalPresetR/aiUpdGimbalPresetR` | `[U]` 未授权写入 |
| Zone preset（tiny2/air） | `aiGetZonePresetListR` 等 | `[X]` 非 Tail2 路径 |

## 6. 媒体（Media）

| 能力 | API | 状态 |
|---|---|---|
| 流操作（Tail2） | `cameraSetMediaOperateParamR(DevMediaStreamId, DevMediaParamOperation)` | `[A]` Capture/Record Start/Stop 均 rc=0 |
| 流回读 | `cameraGetMediaOperateParamR(…,DevMediaParamOperation&)` | `[V/部分]` record 恒 Stop；**capture getter rc=-1** |
| 流枚举 | `DevMediaStreamId{Auto,Record,Capture,Live,Rtsp,Ndi,Srt,Uvc,Kcp,Hdmi,Sdi,RecordSub=16,…}` | — |
| 编码参数（Tail2） | `cameraSet/GetRecordEncodeParamR`、`cameraSet/GetOutputEncodeParamR`、`cameraGetLiveEncodeParamR` | `[U]` |
| 旧拍照/录像 | `cameraSetTakePhotosR/cameraSetVideoRecordR`（Tail Air） | `[X]` 不用于 Tail2 |
| 新版媒体文件通知 | `kEvtInfoNewMediaFile` + `CameraFileNotify{storage_type,file_type,file_path,…}` | `[U]` 通知回调文档标 tail air |
| 文件下载 | `startFileDownloadAsync`/`setLocalFilePath` | `[X]` 文档标 meet/tiny2 series，**Tail2 取回路径未文档化** |

**真机结论**：UVC 下 setter rc=0 但 record 回读恒 Stop、capture getter 失败；现场无 SD 卡，**文件级不可判定**；手册 v1.0 + 操作者确认 UVC 与机内录像互斥。→ MVP 采用 `host_uvc` Provider（产品已拍板）。

## 7. Tail2 AI 控制参数（`DevControlParaType`，`aiSetControlParaR/aiGetControlParaR`）

`DevControlTargetType{Human=0,Animal,Object}`。参数（M1 构图/跟踪原语的直接底座）：

| # | 参数 | 类型 | 用途 |
|---|---|---|---|
| 0 | Motion | bool | 标准/运动跟踪模式 |
| 1 | ForeTrack | bool | 丢失后向前跟踪 |
| 2 | Composition | bool | 用邻近人体自调构图偏移 |
| 3 | TrackerType | int | `DevTrackType{Normal,LimitArea}` |
| 4 | GimCtrlMode | int | `DevGimCtrlMode{Normal,PRO}` |
| 5 | GimCtrlSpeedMode | int | SuperLazy…Crazy/Custom=100 |
| 6 | PanGainAdaptive | bool | |
| 7 | PanGainValue | float | |
| 8 | PanLocked | bool | pan 轴锁 |
| 9 | PitchGainAdaptive | bool | |
| 10 | PitchGainValue | float | |
| 11 | PitchLocked | bool | pitch 轴锁 |
| 12 | AutoZoomCustomized | int | 自定义自动变焦档 |
| 13 | AutoZoomMode | int | 自动变焦模式 |
| 14 | OffsetAdaptiveX | bool | 水平构图偏移自适应 |
| 15 | OffsetX | float | 水平构图偏移值 |
| 16 | OffsetAdaptiveY | bool | 垂直构图偏移自适应 |
| 17 | OffsetY | float | 垂直构图偏移值 |
| 18 | LimitAutoSelection | bool | 限制区自动选人 |
| 19–22 | LimitPan/Pitch Min/Max | float | 跟踪范围限制 |
| 23 | AutoZoomSpeed | int | 自动变焦速度 1–10 |

→ 这组是**实现“构图原语”的正路**（比 `aiSetTargetZoomTypeR` 更细）。本探针已加 `ai.control.get/set` 通用读写，待真机逐项探测当前值与可写性。

## 8. 云台参数（`DevGimbalParaType`，Tail2 全支持）

PanMin/Max、PitchMin/Max(float)、PanReverse(bool)、PresetSpeed(float，tail air 也支持)、RollBias(float)。→ M1 用于建立视角边界与预设速度。

## 9. 手势（`DevGestureParaType` / `DevGestureTrackParaType`，Tail2）

手势开：Gesture/TargetSelection/Zoom/Snapshot/Rolling/Mirror(bool)、ZoomFactor(float 100x)。手势跟踪：Pan/Pitch Min/Max、HandType、TrackSpeed、Pan/PitchEnabled、RestSeconds。→ 桌面/直播现场可用，但手势会与 Agent 控制竞争，M1 需控制权策略。

## 10. 相机 IQ / 对焦 / 白平衡（Tail2 文档）

对焦：`cameraSetAutoFocusModeR/Get(DevAutoFocusType)`、`cameraSet/GetAFCTrackModeR(DevAFCType)`、`cameraGetFocusAbsolute(focus,auto)`；白平衡：`cameraGet/SetWhiteBalanceR(WhiteBalanceSetting)`；`cameraGetConfigRange`（媒体编码范围）。→ 观察质量与“人脸清晰”原语可用。

## 11. 状态与回调

- `aiGetAiStatusR(AiStatus*)`：含 `ai_main_mode/ai_track_sub_mode`（Tail2）、`presets_num` 等（`[V]` 可读）。
- `cameraStatus()` + `DevStatusCallback`：Tail 系列 union（`tail_air`）含 `media_flags{mirror,flip,portrait,hdr}`、`media_running{record_status,capture_status}`、`digi_zoom_ratio`、`online_status{sd_insert,...}`、`usb_status`、`battery` 等（`[U]` 探针未解析，M1 可加安全解析）。
- `Devices::setDevChangedCallback`：插拔热插拔（`[U]`）。
- `Device::setDevEventNotifyCallbackFunc`：事件枚举（图像/视频/错误，`RmEventType`），**文档标 tail air**（`[U]`）。

## 12. 未提供 / UNKNOWN（必须显式保留）

- **Native candidate 列表**：只有 `DevCDCNotifyTypeAiTarget` 枚举，无订阅/payload/坐标路径 → `[X]`（本项目按 host detector / agent_box 走）。
- **设备实时 tracking box 回读**：无 → 页面不得画“实时跟踪框”。
- **机内文件取回（Tail2）**：未文档化 → `host_uvc` 为 MVP Provider。
- **UVC 与机内录像关系**：SDK 不表达；手册+操作者称互斥。

## 13. 探针 op 覆盖（native/main.cpp）

`hello / device.list / device.open / device.status / candidates.probe / target.select(box|center|largest|clicked) / target.clear / framing.set / track.set / track.mode(ai.track_mode) / ai.select_biggest / ai.select_central / look.stop / look.nudge / look.status / zoom.set|get|range / ai.auto_zoom / ai.control.get|set / capture.device / record.start|stop / position.list / position.recall / position.save(拒绝) / shutdown`

## 14. 真机验证汇总（M0 + M0.5）

- Windows x64 构建 + **59/59 离线测试**（含 native）。
- UVC 单属主 + 固定只读预览页（候选/requested ROI/ai/云台三轴 updated）；agent 读图闭环；`host_uvc` photo = 请求后**新帧** artifact。
- 云台速度/停止 `[V]`；`gimbalGetAttitudeInfoR` 间歇失败 → last-good/stale。
- 显式变焦 `[V]`；景别/自动变焦 `[A]` 弱。
- 选框 `[A]`；`ai_main_mode` 仅 Center/Largest 会置 2；主动跟随依赖设备端跟踪是否开启（重启 UVC 后可跟随）。
- 媒体 setter `[A]`、回读异常、无 SD → 文件级 indeterminate。
- 预置 len=0；native candidate `[X]`。

## 15. 给 M1 原语层的建议

1. **Target/Track/Framing 语义独立，Adapter 诚实记录副作用**：`target.select` 是否开启跟踪、是否改 zoom 需按真机写回 `sdk_reported.side_effects`。
2. **构图优先走 `aiSetControlParaR`**（Offset/AutoZoomMode/Composition/PanLocked），而非仅 `aiSetTargetZoomTypeR`。
3. **跟踪启动显式化**：先读/建立“设备端跟踪开关”状态（手势/App/`aiGetAiStatusR`），再下发选框。
4. **坐标标定**：UVC→SDK ROI 需真机左/中/右、上/中/下；镜像/裁切/变焦使旧坐标失效；`camera_epoch` 变更即失效。
5. **状态一律 last-good + source time + stale**（gimbal/zoom/media/ai mode）。
6. **发现用 bounded polling + 热插拔回调**；UVC 重连 bump `camera_epoch`。
7. **媒体走 `host_uvc`**；device-native media 标 `experimental/unsupported`。
8. 保留 `native_candidates` 为外部信息任务，阻塞时走 host detector。
