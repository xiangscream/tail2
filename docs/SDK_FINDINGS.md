# SDK 核对与能力事实

> **Superseded (2026-09-21):** see [`Tail2_SDK_TRUTH_MAP.md`](Tail2_SDK_TRUTH_MAP.md)
> v1.0 for measured truth, and `docs/Tail2_SDK_CENSUS.md` for the
> completeness-gated symbol inventory. Several statements here (native gimbal
> `[U]`, preset/recall untestable, media setters accepted) have since been
> measured; treat this file as the M0 record only.


核对对象：用户提供的 `libdev_v2.1.0_8`，2026-09-20。头文件与库只在授权环境使用，仓库不附副本。

`include/dev/dev.hpp` SHA256：
`d6f12cd9ab50c696b5a2cf9224dda3fc72245e17408bf52dd98d631cb7f74f2d`

包名、头文件版本常量与 Linux 库文件名的版本表达不同，追溯以包标签和哈希为准。后续更换 SDK 必须重跑 `tools/sdk_audit.py`。

## 1. 声明可以支持哪些工作

| 能力 | 本包位置 | 当前结论与 M0 处理 |
|---|---|---|
| 指定具体框 | dev.hpp 4946–5052，DevTargetSelection / aiSetSelectedTargetR | Tail2 类别有 Box、human/animal/common 和归一化 ROI；可写探针，真机效果 pending |
| 全身/半身/特写 | 5062，aiSetTargetZoomTypeR | Tail2 明确声明；配置回读与视觉效果分别验证 |
| 全部候选框 | 4476，DevCDCNotifyTypeAiTarget | 仅通知枚举；没有找到完整订阅/解码/列表路径，UNKNOWN |
| 开关 Tracking | 1923，aiSetEnabledR | 类别说明列旧设备；Tail2 实测前用 legacy-probes 开关隔离 |
| 云台速度与角度读回 | 1956 / 1970 | 可编译声明；方向、单位与 Tail2 行为需现场确认 |
| 云台预置 | 2716 / 2778 / 2805 | 枚举和召回可探测；DevDataArray.len 单位未解释，保存暂不执行 |
| Tail2 媒体控制 | 3412 / 3423 | stream_id + operation，明确 Tail2 类别；UVC 模式是否允许需独立核对 |
| AI 状态 | 1809，AiStatus | 字段含 Tail2 主/子模式；回读 raw，不能宣告目标绑定成功 |
| 通用状态回调 | CameraStatus 与回调声明 | union 的 Tail2 数据布局未明确；只计数/时间，不强行解析 |

选框结构要求 zoom / view 至少一项有效。M0 选用 Normal zoom（关闭自动缩放）加 ignored view，响应注明副作用；随后显式设置 Framing。选框是否自动启用跟踪也必须实测。

`aiSetGimbalMotorAngleR` 实际形参顺序是 pitch、yaw、roll；不要从示例注释倒推 pan/pitch 顺序。当前探针使用有限速度指令，避免扩大未知动作。

通用 `cameraStatus()` 注释提示缓存可滞后 2–3 秒。M0 不拿它当瞬时真相。typed getter 也需要测时效，视觉稳定必须另查图像。

## 2. 必须重新核实的媒体假设

厂商《OBSBOT Tail 2 User Manual_EN_v1.0》，印刷页 17 的 Output 段规定：开启 UVC 后，NDI、机内录像、直播、RTSP、SRT 不可用。当前可读取来源是厂商手册的公开镜像，当前设备固件是否改变此行为仍需实测。[手册镜像](https://device.report/m/8a37de903383bb72a7a581af20b226d07eff027398bf420a87daf19ef96feb77)

因此，“USB/UVC 观察 + 同时机内录像”不能作为已确认能力。本项目保持 USB 输入，M0 首先记录该模式下 Capture / Record 请求、状态与实际文件结果。不要看到 Tail2 媒体 API 就推定所有输出模式均能使用。

旧的 `cameraSetTakePhotosR` / `cameraSetVideoRecordR` 注释属于 Tail Air，M0 不用它们替代 Tail2 明确的 media operation 路径。包内若干资源下载 API 的类别也未覆盖 Tail2，机内图片/视频自动下载仍 pending。

## 3. 候选 Provider 决策

Native candidates 在此轮为 **UNKNOWN**。存在通知枚举不足以实现候选列表。

本地 Agent 可检查正式说明或向 SDK Owner 询问 payload、时间戳、坐标空间、订阅方式、设备模式限制。未取得正式路径时，不尝试猜测 union 或原始缓冲区；继续测试 PC Provider。

M0 提供 OpenCV HOG 人体候选作为台架基线，明确 `provider=opencv_hog_bench`。它不支持本项目所需的全部动物/通用目标，后续检测器选型保留。

## 4. 当前事实记录

| 验证项 | 结果 |
|---|---|
| 私有头文件静态检查 | 已完成 |
| Linux x86_64 真 SDK 编译链接 | 已通过 |
| 无设备协议和错误处理测试 | 已通过 |
| Windows x64 编译 | PENDING |
| Tail2 USB 控制与 UVC 同时打开 | PENDING |
| 多对象 Box 实际选中与持续跟踪 | PENDING |
| Native candidate 列表 | UNKNOWN |
| 当前固件 UVC 与机内录像兼容 | PENDING，手册限制已记录 |
| 完整 Agent / 真实模型调用 | NOT_IMPLEMENTED |

## 5. 外部参照的使用范围

[Reachy Mini core concepts](https://huggingface.co/docs/reachy_mini/SDK/core-concept) 与 [应用文档](https://huggingface.co/docs/reachy_mini/API/apps) 支持“应用通过统一设备访问层运行”的设计参考，不用于推定 Tail2 能力。其应用锁也不能被理解成所有直接 SDK 客户端的统一互斥；本项目另做单写者约束。

[OpenCV VideoCapture](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html) 指出采集行为经过后端、驱动与硬件；读取返回、属性值与实际设备行为需要分别检查。M0 记录实际图像尺寸，并单独要求物理设备绑定。

[Boost.JSON](https://www.boost.org/library/1.82.0/json/) 说明 header-only 模式在一个翻译单元包含 `boost/json/src.hpp`；Windows 定义 `BOOST_JSON_NO_LIB` 避免自动链接未提供的 JSON 库。

[OBSBOT 官方下载页](https://www.obsbot.com/download/obsbot-tail-2) 用于取得对应设备手册、固件与官方工具。M0 不自动升级固件，先记录现场版本。
