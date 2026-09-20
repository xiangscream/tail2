# 当前交接

2026-09-20 · Tail2 Embodied Agent MVP

当前开发基线：`kickoff/embodied-m0-20260920 @ 3609199f13fc06e5a0af9c71d0723aa1421a3fec`。

## 已完成

M0 + M0.5 基础设施已合入：

- Windows x64 / 真 SDK 构建通过；本地报告 71/71，GitHub CI 四矩阵通过。
- 单 UVC 属主 Observation Service；按设备名绑定，断线重连 bump `camera_epoch`。
- frame-bound Observation / Candidate / Target 引用；Target 下发前校验 session / epoch / freshness / calibration / candidate membership。
- `host_uvc` photo / record 基础实现；photo 严格取请求后的新帧。
- localhost 只读预览页：preview、candidate、requested ROI、AI 状态、云台 last-good/stale。
- bounded device discovery；gimbal getter 失败使用 last-good + stale。
- Target Box / Center / Largest / Clicked、zoom、ai.control read probe 等已加入 native 探针。
- `ai.control` 已改为文档化 allowlist；set 默认关闭。
- SDK 能力底座：`../Tail2_CAPABILITY_MAP.md`。

真机关键发现：

- `target.select(Box)` 被接受但不会自动进入 Track；Center/Largest 会把 `ai_main_mode` 置为 Track。
- 设备端 Track 已开启时，目标运动会带动 yaw；SDK 侧 Track 启动语义仍需收敛。
- `framing.set(Full/Half/Close)` 视觉变化弱；显式 zoom 真机有效。
- Native candidate list 无可用正式接口；MVP 继续以 Host Detector 为主 Provider。
- UVC 下 device-native Record 不进入 MVP 主链；默认 media Provider 为 `host_uvc`。

脱敏报告：
- `inbox/2026-09-20-m0-windows.md`
- `inbox/2026-09-20-m0-5-target-loop.md`

## 当前未完成的核心问题

M0.5 的基础运行时成立，但下列产品语义仍未冻结：

1. **Track enable**：设备端真正进入 Track 的可重复 SDK / 状态路径。
2. **ROI mapping**：UVC → SDK ROI 的真实左/中/右、上/中/下现场标定。
3. **Framing execution**：Full / Half / Close 应如何组合 auto zoom、composition、offset 与显式 zoom。
4. **Agent Observation**：未来 Agent 必须使用 frame-bound Observation 原子对象；状态页 `preview.jpg + overlay` 仅用于观察，不是正式 Target 引用。
5. **Media reconnect**：host_uvc recording 遇 camera_epoch 变化时需要 abort / finalize 规则。

现在仍不能把 Target / Track / Framing 全部标成 Agent-ready。

## 本地 Agent 下一步

Issue #4 继续，先做**只读实验**：

1. Human `ai.control.get` para 0–23：Normal 与设备端 Gesture Track 两态 dump + diff。
2. 记录两态下 `ai_main_mode / ai_sub_mode / gimbal / zoom`。
3. 四条窄序列：
   - Normal → Box
   - Normal → Center → Track → Box
   - Normal → Largest → Track → Box
   - Gesture Track → Box
4. 只在上述结果明确后，再进入构图相关参数的单参数 GET → SET → Observe → Restore。

ROI 标定必须使用真实不同现场位置并记录实际 SDK 选中结果。当前 CalibrationStore 的 verified 视为受监督操作员门禁，不代表自动几何证明。

不要开始多模态 Agent、Application、网络视频路线或大范围 ai.control 写扫描。

## 进入 M1 的门槛

当以下两条有可重复结果后，网页端正式冻结 M1 Capability Runtime：

- 具体 Target 能在明确 Track state 下稳定被设备接管；
- Framing 至少有一条可解释的执行路径并能用新 Observation 验证。

Issue #4：<https://github.com/xiangscream/tail2/issues/4>
