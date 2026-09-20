# 当前交接

2026-09-20 · Tail2 Embodied Agent MVP

当前开发基线：`kickoff/embodied-m0-20260920 @ d7249cac464a61882088c062cd11796f0cb1a914`。

## 已完成

M0 首轮 Windows / 真机 bring-up 已回读并合入 kickoff：

- Windows x64 Release 构建与 29/29 测试通过；
- Tail2 UVC 枚举和名称级设备绑定通过；
- UVC Snapshot 可取得；
- `look.stop`、`track.set(false)` 与小范围 gimbal speed 真机有效；
- 状态页只读端点通过；
- 原生候选列表没有找到正式接口；
- UVC 下机内 Record 不作为 MVP 主路线；
- Boost.Container Windows autolink 修复已合入。

原始脱敏报告：`inbox/2026-09-20-m0-windows.md`。

产品与架构裁决：`../M0_DECISIONS_2026-09-20.md`。

## 当前未通过的核心链

**Target B 仍未完成。**

必须验证：

`UVC Observation → calibrated ROI → target.select(box) → concrete target → Tracking → Framing → new Observation`

现在不能把 Target / Framing 写成 Agent 可用的完成能力。

## 已冻结的下一阶段选择

- Candidate：Host Detector 为主 Provider；Agent bbox 为 fallback。Native candidates 不阻塞项目。
- Media：MVP 默认 `host_uvc`。观察、photo、record 共享一个 UVC 采集进程。
- 状态页：允许增加 localhost 预览、候选框、requested ROI、云台 last-good 状态；没有 native 来源时不显示“实时跟踪框”。
- 单写者：一个 Observation Service 独占 UVC；状态页和 Agent 不再单独打开设备。
- Position/Preset、device-native media 与 SDK Owner 的 candidate 询问为 P1。

## 本地 Agent 下一步

执行 M0.5：ROI mapping + Box / Tracking / Framing + 长驻 Observation Service。

从 kickoff 精确基线开新分支，先读：

1. `docs/M0_DECISIONS_2026-09-20.md`
2. `docs/CAPABILITY_CONTRACT.md`
3. 下一轮 GitHub issue

不要接多模态模型，不开始 Application，不切网络视频路线，不上传真实人物图像。

M0.5 通过后，网页端开始 M1 Capability Runtime 的正式实现与审查。
