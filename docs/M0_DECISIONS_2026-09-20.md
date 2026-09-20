# M0 回读后的产品与架构裁决

2026-09-20

本文件把 Windows / Tail2 真机回读转成下一阶段的开发边界。来源为 `docs/handoff/inbox/2026-09-20-m0-windows.md`，基线已并入 `kickoff/embodied-m0-20260920`。

## 1. M0 当前结论

M0 的硬件接通与基础控制通过：Windows x64 构建、SDK 设备枚举、USB/UVC 观察、停止路径和小范围云台控制均已有真机结果。

核心 MVP 闭环尚未通过。以下两项仍是阻塞项：

1. UVC 图像坐标到 Tail2 SDK ROI 的映射没有完成现场标定。
2. `target.select(box)` → 具体对象 → Tracking → Framing 的真实链路没有跑通。

因此可以开始 M1 的基础设施开发，但不能宣布 Target / Framing 原语已经完成，也不进入 M2 视觉 Agent 演示。

## 2. Target Candidate Provider

当前 SDK 没有可用的原生候选列表接口。对 MVP 的工程判断改为：

- `native_candidates`：不进入当前关键路径；保持 SDK 能力记录为 unknown / unavailable-for-mvp。
- `host_detector`：M1 的主 Candidate Provider。它在同一 UVC Observation 上产生候选框。
- `agent_box`：显式 fallback。多模态 Agent 可以直接返回 bbox，但仍经过 Observation / calibration / freshness 校验。

Agent 的职责保持“在候选中语义选谁”。本地 Perception Provider 尽量负责“画面里有哪些候选”。

M1 先实现 Provider 接口和 HOG 台架 backend 以验证数据流。正式检测模型单独选型，需同时考虑人物召回、延迟、许可、部署体积和离线运行。不要把 HOG 的效果当成最终 Target 能力。

## 3. 媒体 Provider

MVP 正式选择 **host_uvc** 作为 Capture / Record 的默认 Provider。

原因是 Agent 视觉闭环已经固定使用 USB/UVC，现场与手册均显示该模式下机内 Recording 不成立；当前 SDK 也没有提供可靠的 Tail2 文件取回路径。继续把 device-native media 放在主链会阻塞与 MVP 目的无关的问题。

语义：

- `observe.snapshot`：一次观察，可短期保存或仅驻留内存，用于 Agent 理解环境。
- `capture.photo(provider=host_uvc)`：从共享 UVC 流取得请求之后的新帧并持久化，返回真实 artifact。
- `record.start(provider=host_uvc)` / `record.stop`：共享 UVC 流写入本地主机文件；stop 完成文件 flush/finalize 后返回 artifact。
- device-native Capture / Record 保留为实验 Provider，不进入 Agent 默认工具面。

首版 host_uvc Record 只承诺视频，不承诺音频、最终编码规格或与 Tail2 机内录像等价。

## 4. Observation Service 与状态页

M1 建立一个长期运行的 **Observation Service**，它是 UVC 的唯一读取者。Agent、候选检测、Capture / Record 和状态页全部消费同一条流，禁止各自创建第二个 VideoCapture。

状态页继续是只读工程页，可以增加：

- localhost 实时低频预览；
- Candidate boxes；
- 当前选中的 **requested target ROI**；
- 云台角度的 last-good value、时间与 stale 状态；
- Agent 未来使用的 Observation / Capability / SDK / Result 时序。

当前 SDK 没有原生 Tracking box 来源，因此页面不得把 requested ROI 或 detector box 标成“设备实时跟踪框”。

真实图像不写公开 trace；状态页只绑定 localhost，响应设置 no-store。OBSBOT Center 或其他 UVC 消费者存在时给出冲突提示，不自动杀进程。

## 5. 状态与发现规则

M0 说明固定 3 秒枚举不可靠。M1 改为 bounded discovery：

- 在总 timeout 内轮询设备；
- 只接受显式 Tail2 UVC 设备；
- 成功绑定后再进入 ready；
- timeout 返回 unavailable，不继续执行写操作。

legacy `gimbalGetAttitudeInfoR` 有间歇失败。状态聚合器保存 last-good value、source time 和 error；一次查询失败将状态标记 stale / unknown，不把角度清零。

SDK `rc=0` 仍只表示请求被接口接受。Target、Framing、媒体完成需要设备状态或视觉 / artifact 结果。

## 6. M0.5：进入 M1 前必须跑通的具体链路

M0.5 只处理当前两个阻断点和它们需要的最小工具：

1. 长驻 UVC Observation Service + 状态页实时预览。
2. 同设备绑定与 UVC → SDK ROI 标定；至少验证左 / 中 / 右和上 / 中 / 下。
3. 人工框直接调用 `target.select(box)`，记录是否选对具体人，以及它对 Tracking / Zoom 的副作用。
4. Full Body / Half Body / Close Up 真机验证；同时保留 SDK requested state 与视觉结果。
5. 从同一流实现 host_uvc photo；video recording 可以随后接入，不阻塞 Target 链。
6. 状态读取使用 last-good / stale 语义。
7. 页面展示 Candidate / requested ROI，不声明 native tracking box。

完成后，M1 才把 Target / Track / Framing 加入可供 Agent 使用的正式能力列表。

## 7. P1，不阻塞核心链路

- Position / Preset：当前列表为空。需要显式允许后再创建临时测试预置，验证 recall 与清理；不阻塞 M1 Target 链。
- Native candidate SDK Owner 询问：继续作为外部信息任务，不阻塞 host detector。
- device-native media：只有在另一个不占 UVC 的模式下有明确价值时再做专项验证。
