# 当前交接

2026-09-21 · Tail2 Embodied Agent MVP

当前阶段：**M1 Capability Runtime**

开发分支：`m1/capability-runtime`
阶段任务：Issue #8
M0/M0.5 结项基线：`704b7fc2054e85d850ec2969964a17abc307cad3`

## M0/M0.5 已冻结结论

- Observation Runtime：PASS。单 UVC 属主，frame-bound Observation / Candidate / epoch。
- Target/Track：PASS。Normal 下 Box 不启动跟踪；先进入 Track runtime，再 Box 具体目标。
- Track entry：Center/Largest 或设备端手势；当前 canonical readback 为 `aiGetAiStatusR().ai_main_mode`。
- ROI：当前 640×480 / 1x / 横向 profile 下 **identity VERIFIED**；双目标 target-switch 已排除 Center 假阳性。
- Look/AI ownership：PASS。手动云台前关 AI，恢复跟随时显式恢复 AI/Track。
- host_uvc media：基础 PASS；recording 跨 reconnect 收尾进入 M1。
- Framing：显式 zoom 有效；TargetZoomType 视觉弱；已试 Offset 路径没有有效 Tail2 构图偏移结果。
- Native candidate list / tracking bbox：无可用正式接口。

最终 M0.5 报告：
`inbox/2026-09-20-m0-5-state-sequences.md`

原语映射：
`../M1_PRIMITIVE_LAYER_NOTES.md`

M1 计划：
`../M1_CAPABILITY_RUNTIME_PLAN.md`

## M1 目标

把已验证设备事实封装成正式中层原语：

`Observation / Target / Track / Framing / Look / Capture / Record / Status / Stop`

M1 不接模型。先让确定性脚本使用同一套 Capability 完成闭环，M2 再接多模态 Agent。

## 第一轮：M1A

只做 Runtime foundation：

1. CapabilityRequest / CapabilityResult / errors / lifecycle。
2. task_id / request_id / continuation_id；正式支持 REOBSERVE_REQUIRED。
3. StateRegistry：requested / sdk_reported / visual_check / artifact 分离。
4. ResourceOwnership：DeviceWriter / LookOwner / MediaOwner。
5. 单写者队列、cancel、deadline、indeterminate。
6. native bridge timeout / exit 后显式 session rebuild。
7. 保持现有 Observer / ObservationService / Bridge 可运行，先包住，不大爆炸重构。

M1A **不新增真机动作策略**。先把当前已经知道的动作放进正式 Runtime 边界。

## 后续顺序

- M1B：Target + Track 金链。
- M1C：Look ownership + host_uvc reconnect。
- M1D：centered Framing Solver。
- M1E：无模型端到端脚本 + 状态页 trace。

## 本地 Agent 协作

本地 Agent 后续从各小 PR 的 exact HEAD 做真机回读；不直接在 kickoff 或 M1 主开发分支上混写。

M1A 默认只需离线开发与测试。需要真机前由网页端明确给出 experiment matrix。

Issue #8：
<https://github.com/xiangscream/tail2/issues/8>
