# M0.5 报告：Observation Service、ROI/Target、变焦与能力底座（脱敏）

日期：2026-09-20
分支：`local/m0-5-target-loop`
基线：`d8eec2beca3ebbb3f9efd8457b8ff9f2e56621f8`（`origin/kickoff/embodied-m0-20260920`）
任务：Issue #4

本文件只写脱敏结论；SDK、头文件/库、真实图像、原始日志、序列号与凭据留本地（`.local/`）。

## 1. 交付物

代码（`tail2_mvp/`）：
- `observation_service.py`：**单 UVC 属主** Observation Service；snapshot、`host_uvc` photo（严格取请求**之后**的新帧）、`host_uvc` record、低频预览 JPEG、候选检测；**UVC 断线重连**（重连 bump `camera_epoch`）。帧源支持 **按设备名绑定**（`resolve_dshow_index`，pygrabber 解析 DirectShow 名称）或显式 index。
- `calibration.py`：UVC→SDK ROI 标定模型（verified 标志、mirror_x、rotation 0/180、crop、zoom）。
- `state.py`：`LastGood`（last-good + source time + stale + error）、**bounded discovery**、UVC 冲突检测。
- `observer.py`：受监督编排（UVC 服务 + native bridge + 只读状态页），命令通道（stdin 或 `--command-file`）、云台/ai 轮询、Target/Track/Framing/Zoom/媒体命令；HOG 与 **face 台架** backend。
- `status.py`/`status.html`：只读 localhost 页，新增预览、候选框、requested ROI、ai 模式、云台三轴 last-good/stale；`img-src 'self'`、no-store、loopback。
- `__main__.py`：新增 `observe` 子命令。

native 探针新增 op：`target.select(box|center|largest|clicked)`、`ai.select_biggest/central`、`ai.track_mode`、`zoom.set/get/range`、`ai.auto_zoom`、`ai.control.get/set`（**文档化 allowlist + 每参数类型/范围，去掉了 ±1e6**）。

文档：`docs/Tail2_CAPABILITY_MAP.md`（Tail2 能力底座，供 M1 原语层）。

测试：**71 项全部通过**（Python + 6 native）。Windows x64 Release + MSVC 19.44 + SDK 10.0.26100。

## 2. 真机结果

环境：Tail2（alias `Tail2-A`）、固件 `7.2.9.41`、USB VID_3564 / PID_FEFC。

### 2.1 Observation（通过）
- 单 UVC 属主 640×480，固定只读页 `http://127.0.0.1:8800`：预览 + candidate + requested ROI + ai + 云台三轴，均正常。
- **agent 视觉闭环 PoC**：直接拉 `/api/preview.jpg` + `/api/overlay` 渲染 `agent_view.png`，可读图确认（本会话已多次读图核对）。
- `host_uvc` photo：frame_seq 严格递增（如 210→211），返回 `media_id/path_ref/sha256/finalized/accessible=true`，manifest 落盘。
- 按设备名绑定：`device_name='OBSBOT Tail 2 Camera'` → 解析 index 1；设备缺失时明确报错，不再误读“OBSBOT Virtual Camera”。

### 2.2 Target / Track（部分，关键发现）
- `target.select(Box)`：SDK rc=0，但 **`ai_main_mode` 保持 0（Normal）**。
- `target.select(selection=Center/Largest)`：**`ai_main_mode` 置 2（Track）**。
- `aiSetAiTrackModeEnabledR(AiTrackHumanNormal,true)`：rc=0，但 **未改变 `ai_main_mode`**；legacy `aiSetEnabledR(true)` 同样无效。
- 偏置目标下（人 cx≈0.65）box 选择后云台 yaw 不变、face 未居中。
- **主动跟随可成立**：在一次 UVC 重启 + 设备端跟踪开启（手势蓝灯）后，纯读采样显示 **yaw 随人走动持续变化**（-108→-105→-116→-90→-113…，ai=2），后期 box 选人剪影下 yaw 6.1→18.3。→ **跟踪主责可能在设备端跟踪开关，SDK 选框未必自动开启**。
- 无 native tracking box 回读（页面据此只画 requested ROI）。

### 2.3 Framing / Zoom
- `framing.set(close_up/half_body/full_body/normal)`：rc=0，但 face 框高 0.358/0.354/0.315/0.363，**视觉景别变化很弱**（full_body 略小）。
- `aiSetAiAutoZoomR(true)`：rc=0，未显著改变。
- `cameraSetZoomAbsoluteR(zoom, speed)`：**真机有效、可见**。`zoom.set(1.5)` 后 `zoom.get=1.12`（异步滞后），face 高 **0.342→0.821**；`zoom.set(2.0)` 过近出框；`zoom.set(1.0)` 回退。`zoom.range`=`{0,100,1,0,valid}`，`zoom.get` 归一化 1.0+。文档类别未列 tail2，但实测有效（同 gimbal speed）。

### 2.4 媒体
- `cameraSetMediaOperateParamR(Capture/Record,Start/Stop)` 均 rc=0；但 `cameraGetMediaOperateParamR(Record)` 恒为 Stop，`(Capture)` **rc=-1**。现场**无 SD**，文件级不可判定；手册 v1.0 + 操作者确认 UVC 与机内录像互斥。→ MVP 走 `host_uvc`。

### 2.5 预置 / 候选
- `aiGetGimbalPresetListR` rc=0、len=0（无预置，无 ID 可 recall）；`position.save` 拒绝。
- native candidate：无正式接口 → UNKNOWN。

## 3. 稳定性/环境问题（需 M1 处理）
- `device.list` 固定 sleep 不可靠（3s 曾空、8s 稳定）→ 已改 **bounded discovery**。
- `gimbalGetAttitudeInfoR` 间歇 `rc=-1` → 已改 **last-good + stale**，不清零。
- UVC 重枚举后 index 漂移（真实相机消失、虚拟相机占据 index）→ 已改 **按设备名绑定**。
- 设备曾出现 USB 枚举失败（`VID_0000&PID_0004`，Code 43，设置地址失败）；`pnputil /restart-device`、禁用/启用、重启父集线器均无效，**断电重插后恢复**。
- OBSBOT Center/OBSBOT_Main 运行会独占 UVC；服务只提示、不自动杀进程（符合规程）。

## 4. 未完成 / 下一步
- `ai.control.get/set`（Tail2 构图/跟踪参数：Offset/AutoZoomMode/Composition/PanLocked 等）尚未真机逐项扫描——多次因设备未以 UVC 枚举而中断。
- UVC→SDK ROI 的**镜像/左中右/上中下标定**未完成（当前 identity 标定，verified 仅台架）。
- Full/Half/Close 的**视觉闭环**未稳定复现（framing 变化弱；显式 zoom 有效但属底层）。
- 跟踪启动的**设备端状态读法**待定（`aiGetAiStatusR` 与设备跟踪开关的关系）。
- 建议 M1 原语层直接采用 `docs/Tail2_CAPABILITY_MAP.md` §15 的结论。

## 5. 结论强度
- 单属主 Observation、预览页、agent 读图、`host_uvc` photo：**已实测通过**。
- 显式变焦：**已实测可见**。
- Framing 景别：**SDK accepted，视觉弱**。
- Target/Track：**选框 accepted；跟踪依赖设备端开关，SDK 单独选框未证实可启动**。
- 媒体/预置/候选：**indeterminate / len=0 / UNKNOWN**。

## 6. PR #6 review 修复（本轮追加）
按 review 修正四个阻断项：

1. **Observation/Candidate/Target 严格绑定同一帧**：新增 `observations.py`（`ObservationStore`/`ObservationRecord`/`ObservedCandidate`/`ReobserveRequired`）；`ObservationService.snapshot()` 现在**在快照那一帧上同步计算候选**（`candidate_frame_seq == frame_seq`）；`target.select` 必须携带 `observation_id`（或 `candidate_id`），下发前校验 `stream_session / camera_epoch / freshness / calibration_id / candidate 归属`，否则返回 `REOBSERVE_REQUIRED`，**不再“收到命令再拍一张”**。
2. **标定不可自证**：新增 `CalibrationStore`；`calibration.profile` 只设置参数且永远 `verified=false`；`calibration.sample` 必须引用真实 `observation_id`（左/中/右/上/中/下）；`calibration.verify` 只有样本齐全才置 verified 并持久化到 `.local/service/calibration/`；`camera_epoch` 变化自动失效。
3. **`ai.control` allowlist**：native 建立 `DevControlParaType` 文档化表（para/name/kind/range），`ai.control.get` 仅允许 0–23 文档参数，`ai.control.set` 按参数类型与范围收紧（去掉 ±1e6）；观察器**默认禁用 `ai.control.set`**，需 `--allow-control-writes`。
4. **文档测试数统一**：能力地图 §14 与报告统一为 **71/71**。
5. 附加：UVC 重连 bump `camera_epoch` 时清空 candidate；观察器在 epoch 变化时使标定失效并清空 requested ROI。

## 7. 下一轮（按 Issue #4 窄实验）
- 只读 `ai.control` dump（Human, para 0–23）在 `Normal` 与设备手势 `Track` 两态下对比。
- 四条窄序列：Normal→Box；Normal→Center→Track→Box；Normal→Largest→Track→Box；手势 Track→Box。
- 之后再按 GET→SET 单参数→观察→restore 的纪律扫构图相关参数。
