# SDK Sweep D 报告：closure / unsupported / deferred 收口

日期：2026-09-21
分支：`feature/sdk-sweep-d`
基线：从 `feature/sdk-sweep-c` 尖端 `e8efd1e` 分出（**Wave C 尚未合入 main**，见 §5）
设备：**未使用**（Wave D 是静态收口；设备保持关机）
产出：`docs/Tail2_SDK_TRUTH_MAP.md` **v1.0（frozen）** + Appendix A 全量 closure 表

## 0. 结论

Tail2-relevant 家族的**每一个 function/callback（262 个）**都有了明确处置，
**没有任何 architecture-significant 符号留成裸 `[U]`**。Wave D 完成，可以进入
Primitive Layer Freeze 的讨论（只剩两个已登记的 gap，见 §4）。

## 1. 交付

- `tools/closure_table.py`：可复现的 closure 表生成器（输入 census JSON，输出 sanitized markdown；
  实测结果以数据形式内嵌，与 truth map 一致）。
- `docs/Tail2_SDK_TRUTH_MAP.md` 升到 **v1.0 frozen**，新增：
  - §9 Wave D closure（处置统计 + 计划要求的 closure classes + freeze gate 勾选）
  - Appendix A：全量 closure 表（262 行）
- `docs/Tail2_CAPABILITY_MAP.md` / `docs/SDK_FINDINGS.md` 顶部加 **Superseded** 说明，
  并点名已知过期结论（native gimbal `[U]`→其实 VERIFIED、look 不止 ±10dps、offset 实为
  `UNSUPPORTED_TAIL2`、`cameraSetPowerCtrlActionR` 能关机等），避免后人拿旧表做能力决策。

## 2. 处置统计（262 个 HIGH-family function/callback）

| disposition | count | 含义 |
|---|---|---|
| `VERIFIED` | 23 | 真机复现物理/视觉/状态 |
| `READBACK_VERIFIED` | 38 | getter/status 路径已证 |
| `CONSTRAINED` | 5 | 仅在明示条件下可用 |
| `ACCEPTED_UNPROVEN` | 16 | rc 被接受或 header 标 Tail2，但未证 |
| `UNSUPPORTED_TAIL2` | 14 | 实测无效果 / 被拒 |
| `evidence_insufficient` | 9 | 判据无法评估（原因已记） |
| `DEFERRED_UNSAFE` | 15 | destructive/持久，按纪律未执行 |
| `DOC_OTHER_PRODUCT` | 140 | 文档标其它产品、未实测 —— **不是** support 结论 |
| `NOT_PRODUCT_RELEVANT` | 2 | 不属于 Agent Camera MVP |

**为什么 `DOC_OTHER_PRODUCT` 不叫 `UNSUPPORTED_TAIL2`**：Wave A/B/C 已经双向证伪过文档适用性
（整个原生 gimbal 家族文档只写 tailair+tiny 却可用；`cameraSetPowerCtrlActionR` 文档写
tail air 却能把 Tail2 关掉）。没有实测就宣称“不支持”，等于把同一个错误反着再犯一次。
因此它们保持为**显式登记的缺口**，而不是结论。

## 3. 计划要求的 closure classes（全部落位）

| class | 落位 |
|---|---|
| Tail Air / Tiny / Meet 专属、非 Tail2 | `DOC_OTHER_PRODUCT` 集合（Appendix A） |
| 公开 payload 契约不完整 | `DevCDCNotifyTypeAiTarget`（候选通知）、设备侧 tracking box / identity 回读、媒体事件 payload、`CameraStatus` union 布局 |
| tracking box / identity 回读缺失 | 确认缺失：无原生跟踪框，identity 由设备决定 |
| Tail2 未文档化的文件下载 | `startFileDownloadAsync` / `setFileDownloadCallback` / `localFilePath` / `localFileMiniPath`（meet+tiny） |
| 故意未执行的 destructive | `DEFERRED_UNSAFE` 集合（factory reset、gimbal reset、boot position 写、zone reset、indicator clear、文件删除/格式化/升级/下载） |
| 无产品相关性 | TWS/耳机、网络配置、HDMI/NDI box、zone preset |

## 4. Freeze gate（plan §10）状态

- [x] Phase 0 census 覆盖完整 SDK 资源（completeness gate，unmatched 0）
- [x] Wave A 收口
- [x] Wave B 高/中价值能力收口
- [x] Wave C 即使 host_uvc 仍是首选也有明确 truth state
- [x] Wave D 明确记录 unsupported / deferred
- [x] 无 architecture-significant API 留成未解释的 `[U]`
- [ ] **B1b 真人手势会话**（已登记，Primitive Freeze 前补；不阻塞）
- [ ] **C4 receiver 级验证**（可选，需要一台同网段接收端）

## 5. Git 说明（重要）

Wave C（`feature/sdk-sweep-c @ e8efd1e`）**尚未合入 main**（main 仍是 Wave B 的 `9d14848`）。
为避免 Wave D 丢掉 A+B+C 的真值，`feature/sdk-sweep-d` 从 **Wave C 尖端**分出。
⇒ 合并顺序应为 **先 C 再 D**；C 合入后，D→main 的 PR 只会显示 Wave D 的增量（C 成为祖先）。

## 6. 对下一阶段（Pro 级 Primitive Layer Freeze）的输入

`Tail2_SDK_TRUTH_MAP.md` v1.0 现在可以回答计划里那句问题：

> 哪些是稳定 Primitive，哪些是 Solver，哪些是 Adapter policy，哪些是 Agent 编排，
> 哪些槽位未来可以替换成学习出来的 Photographer Policy？

现有的硬输入包括：绝对 Look 可用但**与 Track 争用所有权**；Pan/PitchLocked 是**按轴约束**
而非“关掉 Track”；framing 只有 `ai_sub_mode` 状态回读、数值不可读；offset 数值不可写；
媒体写路径多处 `no_effect_observed`；`FastDevStatusCallback` 不投递；物体跟踪需要 **watchdog**。
