# SDK Sweep C 报告：Media / Output / UVC coexistence 真值闭环

日期：2026-09-21
分支：`feature/sdk-sweep-c`
基线：`main @ 9d14848d1ecd944f541fbdc724c9865fcff7e64b`
设备：Tail2，固件 7.2.9.41，UVC；真实日志在 `.local/sdk-sweep/waveC-log.md`。
本轮**未新增正式 Primitive API / Runtime feature**。

证据框架：`Request → SDK acceptance → Expected Effect Predicate → Evidence → Verdict`，
媒体专用阶梯：`request accepted → state changed → media produced → artifact finalized → artifact accessible`。

产品前提（操作者确认）：**本 MVP 不需要本地 SD 卡**，目标是验证 Agent 实时控制与可二次开发应用，
因此 C2 的 artifact-level closure 记为 `NOT_PRODUCT_RELEVANT`，`host_uvc` 仍是默认 provider。

## 0. 结论摘要

| 能力 | verdict | 关键证据 |
|---|---|---|
| `cameraGetRecordEncodeParamR` | **READBACK_VERIFIED** | 4K/60Mbps/H264；fps=30000 为 milli-fps |
| `cameraGetOutputEncodeParamR` | **READBACK_VERIFIED** | `night=false` 4K/60Mbps ↔ `night=true` 1080p/20Mbps ⇒ **night_flag 是有效参数** |
| `cameraGetLiveEncodeParamR` | **READBACK_VERIFIED** | 1080p/4Mbps；**无 public setter ⇒ 写入 `NO_PUBLIC_PATH`** |
| `cameraSetRecordEncodeParamR` | **CONSTRAINED** | 宽高/码率可写+回读，但**码率按分辨率校验**：4K@20Mbps 被忽略（仍 60Mbps）、1080p@10Mbps 被抬到 20Mbps；`encode_format` 写入不生效（要 H265 仍是 H264） |
| `cameraSetOutputEncodeParamR` | **CONSTRAINED** | 同上（1080p 有效组合生效并已还原） |
| `cameraGet/SetRecordSplitSizeR` | **VERIFIED** | 5→2→5 回读一致 |
| `cameraGetMediaOperateParamR` | **READBACK_VERIFIED** | Uvc=Start(1)；Record/Live/Rtsp/Ndi/Srt=Stop(2)；**Capture rc=−1**；Hdmi/Sdi/sub=Auto(0)；Auto(0) rc=−1 |
| `cameraSetMediaOperateParamR(Record,Start)` | `no_effect_observed` → `prerequisite_unmet` | rc=0 但状态恒为 Stop（3s，UVC 开/关都一样） |
| UVC coexistence | **CONSTRAINED**（部分未达） | UVC 打开时原生媒体命令不影响 UVC 帧流（~29fps 连续）；第二次打开 UVC 失败（单属主） |
| `cameraGetSelectNdiOrRtspR` / `NdiRtspEncoderFormatR` | **READBACK_VERIFIED** | select=0；format=1(H264) |
| `cameraGetNdiRtspBitrateLevelR` | **CONTRACT ANOMALY** | 枚举类型 `DevVideoBitLevelType` 却返回 **60000000**（像裸码率）⇒ 类型/契约不一致 |
| `cameraSetSelectNdiOrRtspR` / `NdiRtspBitrateLevelR` / `HdmiInfoR` | `no_effect_observed` | rc=0，回读不变（文档=tailair） |
| SDI / SRT 配置 | **NO_PUBLIC_PATH** | 只有枚举（`DevMediaParamSdiMode` / `DevSrtMode` / `DevSrtEncryType`），无 getter/setter 函数 |
| 设备内文件取回 | **NO_PUBLIC_PATH** | 下载族文档=meet+tiny，Tail2 无文档化路径 |

## 1. C1 Encode / config readback

- `cameraGet{Record,Output,Live}EncodeParamR` 全部 rc=0 且返回结构：`{width,height,fps,bitrate,encode_format}`。
- **单位**：`fps=30000` 表示 30.000 fps（milli-fps）。这是写 probe 时必须知道的细节（我第一版把 fps 上限设成 1000，直接被 range 拒绝）。
- **`night_flag` 是有效参数**：output encode 在 `night=false` 读到 4K/60Mbps，`night=true` 读到 1080p/20Mbps。
- 写路径：
  - 只改码率（4K@20Mbps）→ **回读不变**；改成 1080p+20Mbps → 全部生效；1080p@10Mbps → 回读被抬到 20Mbps。
  - ⇒ 码率是**按分辨率校验/钳制**的，越界组合被静默忽略。属于 `CONSTRAINED`，不是 no-op。
  - `encode_format` 写入不生效（请求 H265(2)，回读仍 1）。
- `cameraGet/SetRecordSplitSizeR`：5(32GB)→2(8GB)→5，`VERIFIED`。

## 2. C2 Device-native Media operation

`cameraGetMediaOperateParamR` 逐流回读（跳过 Auto(0)，因为它第一次返回 rc=−1 后设备 USB 掉线，因果未证）：

```text
Uvc(7)=Start(1)   Record(1)=Stop(2)   Live(3)=Stop(2)   Rtsp(4)=Stop(2)
Ndi(5)=Stop(2)    Srt(6)=Stop(2)      Capture(2)=rc -1
Hdmi(9)=Auto(0)   Sdi(10)=Auto(0)     RecordSub(16)/LiveSub(17)/NdiSub(18)=Auto(0)
Auto(0)=rc -1
```

`cameraSetMediaOperateParamR(Record, Start)`：rc=0，但 3 秒内状态恒为 **Stop**（UVC 打开/关闭都一样）。
⇒ `request accepted` 但 `state changed` 不成立。因为**没有存储介质**，无法区分“需要 SD 才能启动”与“静默 no-op” ⇒ 按纪律记 `prerequisite_unmet / evidence_insufficient`，**不判 UNSUPPORTED**。

## 3. C3 UVC coexistence matrix（架构重点）

| 场景 | 结果 |
|---|---|
| UVC closed → record.start | rc=0，状态不变；UVC 可用（grab 成功 640×480） |
| UVC open（单属主 preview）→ record.start | rc=0，状态不变；**UVC 帧继续流（~29fps）**，`media.op.get Uvc=Start` |
| UVC open 后再次打开 UVC | **失败**（`can't be used to capture by index`）⇒ PC 侧单属主成立 |
| native active → 尝试 UVC open | **不可达**：没有存储/网络目标，无法让任何 native 流真正 active |

结论：**在“命令被接受但未真正激活”的范围内，未观察到 UVC 与 native media 的冲突**；但“native 真激活 → UVC 是否还能开”这一格因为 prerequisite 不满足而**未测**，不得写成“无冲突”。

## 4. C4 RTSP / NDI / SRT / HDMI / SDI

- NDI/RTSP 读路径可用：`select=0`（都关）、`encoder_format=1`、`bitrate_level` 见下。
- **契约异常**：`cameraGetNdiRtspBitrateLevelR(DevVideoBitLevelType&)` 返回 **60000000**，远超枚举范围 0–3，像把“裸码率”塞进枚举类型 ⇒ SDK/固件契约不一致，写 probe 时不能按枚举解释。
- HDMI `cameraGetHdmiInfoR`：全部 0（osd_language/content/volume/resolution/info_display）。
- 写路径（select / bitrate / hdmi volume / info_display）rc=0 但**回读不变** ⇒ `no_effect_observed`（文档=tailair）。
- **SDI / SRT 只有枚举没有函数** ⇒ `NO_PUBLIC_PATH`；`cameraSetNdiRtspResolutionR` 无 getter。
- “接收端真收到”未做：没有配置网络目标 ⇒ `prerequisite_unmet`。

## 5. C5 Media state / callbacks

- 普通 `DevStatusCallback` 持续投递（~2s，`18→19→20→21` 跨越 record start/stop）；`FastDevStatusCallback` 始终 0；`devChanged` 1 次初始。
- payload 是 `CameraStatus` union，**Tail2 布局无文档** ⇒ 不解析、不猜。
- ⇒ 媒体状态的**权威证据是 `cameraGetMediaOperateParamR` getter**，不是 callback。callback 只可作为“设备还活着/有变化”的信号。

## 6. C6 host_uvc vs device-native 结论

- **device-native 可闭环的**：encode 读回、split size 写读、media operation 读回。
- **只到 READBACK_VERIFIED**：NDI/RTSP/HDMI getter。
- **命令被接受但无效果**：record start（状态不变）、NDI/RTSP/HDMI 写入。
- **prerequisite 未满足**：record/capture artifact（无存储，且 MVP 不需要）、网络输出 receiver、native-active 下的 UVC 冲突。
- **NO_PUBLIC_PATH**：live encode setter、SDI/SRT 配置、媒体事件 payload、Tail2 文件取回。
- **MVP 仍选 `host_uvc`**：因为本 MVP 的目标是“Agent 实时控制 + 可二次开发应用”，不是机内录制；device-native media 在无存储/无网络目标下无法升到 artifact/receiver 级证据，且其写路径多处 `no_effect_observed`。

## 7. 设备/链路风险（必须记录）

- 本次 Wave C 期间出现 **USB 枚举失败**（`Device Descriptor Request Failed`）与非预期掉线：一次在 `PowerOff` 之后，一次在读取 media operation 的中途。物理重插/重启后恢复。
- 影响：**长时媒体实验的可行性受链路稳定性限制**；后续若做 receiver/长时 record，需要先确认线材/端口稳定性。读取 `media.op.get` 时我改为**逐条 + 间隔 + 存活检查**，并**跳过 Auto(0)**。

## 8. 未做 / 下一轮

- receiver 级证据（RTSP/NDI/SRT）：需要网络目标；只到 readback。
- HDMI/SDI 物理 sink：无硬件，不采购。
- 媒体事件回调 payload：无公开契约。
- 有存储时的 record artifact closure：按产品决定不做。
