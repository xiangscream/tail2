# 当前交接

2026-09-20 · Tail2 Embodied Agent MVP

基线分支：`kickoff/embodied-m0-20260920`。首次代码审查通过前保留 Draft PR，main 不变。

## 已完成

开发计划、能力契约、SDK 静态核对、C++ 真 SDK 编译、M0 探针、UVC 单次观察工具、候选契约测试、只读状态页和离线测试。状态和结果详见 `../VERIFICATION.md`。

## 尚未完成

Windows 构建、USB/UVC 真机测试、原生候选订阅、完整中层 Runtime、视觉 Agent、真实照片/录像结果验证。

## 本地 Agent 下一步

按 [M0 操作手册](../M0_RUNBOOK.md) 从只读发现开始，完成同设备控制与图像绑定、坐标映射、停止路径、Box/Framing、媒体模式以及 Preset 适用性核对。原生候选没有文档化路径时保持 UNKNOWN，继续 PC 候选基线。

**优先回答 UVC 与机内 Record 冲突。** 不静默改网络、不把 UVC 截帧写成机内拍照，不自动写预置，不上传真实图像或 SDK。

本地新分支：`local/m0-hardware`，提交脱敏结果至 `inbox/` 并在 kickoff PR 下回报。代码变化附测试，平台选型或功能收缩交给产品负责人决定。

长期事实更新进 SDK_FINDINGS、能力契约和代码；本页只保留当前交接，避免另一套项目真相。
