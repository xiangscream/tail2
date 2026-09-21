# SDK Sweep A 报告：Phase 0 census + Wave A 真机摸底

日期：2026-09-21
分支：`feature/sdk-sweep-a`
基线：`main @ 385fe55005c9e3b075fb454f18ffb9a789e9aab4`
设备：Tail2，固件 7.2.9.41，UVC；操作者在场，OBSBOT Center 关闭；真实日志/图像在 `.local/sdk-sweep/`。
本轮**未新增正式 Primitive API**。

## 0. 一句话结论

**Tail2 存在可靠的绝对角度 Look**，而且原生 Gimbal 家族的文档适用性（只写 tailair+tiny）是错的；
但 `aiSetTargetViewTypeR` 与 zoom 家族的三个写接口属于**静默失败（rc=0 且本轮测试前置下无效果）**，offset 数值在 Tail2 上存不下去。
→ 中间层设计不能再依赖「文档适用性」，也不能把 `rc=0` 当成功。

## 1. 交付物

- `tools/sdk_census.py` + `tests/test_sdk_census.py`（发现式 root inventory；原 10 项 + 7 项 discovery 测试）
- `docs/Tail2_SDK_CENSUS.md`（sanitized，当前生成结果 **479 symbols**；3 public headers + 1 sample + 1 build + 29 binaries，unclassified=0）
- `docs/Tail2_SDK_TRUTH_MAP.md`（v2，Wave A 已回填）
- `docs/Tail2_SDK_EXPERIMENT_MATRIX.md`（Wave A 45 条 + 结果表）
- probe 扩展（`native/main.cpp`）：`gimbal.angle / gimbal.speed / gimbal.native_stop / gimbal.state.get /
  gimbal.para.get|set / gimbal.bootpos.get|trg / gimbal.yawreverse.set / gimbal.pos.speed /
  view.set / framing.get / zoom.relative / zoom.withspeed / zoom.stop`
- 修复前真机构建基线：Windows **119 passed**；发现式 census 修复后本地 Linux **121 passed / 6 skipped**；当前 GitHub CI 的 Windows/Ubuntu × Python 3.11/3.12 四矩阵全部通过

## 2. A1 Native Gimbal / Look —— 架构级发现

| 结论 | 证据 |
|---|---|
| **绝对角度 Look 可用**：`aiSetGimbalMotorAngleR(pitch,yaw,roll)` | 3 次重复：命令 10/20、−10/−20、15/0 → legacy 与 native motor 回读**完全一致**；画面确认 |
| 第二条绝对路径：`gimbalSetSpeedPositionR(roll,pitch,yaw,s_*)` | 命令 5/10 → 回读 5.0/9.98 |
| **原生速度 + 原生停止**可用 | `aiSetGimbalSpeedCtrlR` pan=5 ≈ 5.5°/s；`aiSetGimbalStop` 残余 **≤0.01°**（legacy ≈0.4°） |
| **符号约定**：yaw+ = 左转，pitch+ = 下俯；**原生 speed 的 pan 符号与 legacy 相反** | 画面 + 回读 |
| 绝对控制**被 AI 跟踪争用**（`ai_main_mode=2` 时） | Track 中发 yaw=25：−23.95 → −19.18，未达 25，模式仍 2，目标仍被框住 ⇒ `CONSTRAINED` |
| 真回读：`aiGetGimbalParaR(float&)` 给出真实限位 | Pan ±180、Pitch ±90、PanReverse 0、PresetSpeed 1.0、RollBias 0；**bool 重载对每个 type 都 rc=0/false（陷阱）** |
| `aiGetGimbalStateR` 比 legacy 更全 | euler + motor + 角速度；motor = 命令值，euler = motor + 开机偏置（yaw ≈ −14.2°） |
| `aiGetGimbalBootPosR` 可读 | id 0、0/0/0、zoom 1.0 |
| `aiSetGimbalYawDirReverseR` **无可观测效果** | rc=0，但 PanReverse 回读不变、绝对与原生速度两条路径方向都不变（可能需重启，未追） |
| 预置列表为空 | `len=0` ⇒ `position.recall` 无对象可测 |
| 未执行（`DEFERRED_UNSAFE`） | `aiSetGimbalBootPosR`、`aiRstGimbalBootPosR`、`gimbalRstPosR` |

## 3. A2 AI Control 0–23

- 24 项全部可读；**23/24 可写且回读一致**（bool 需传 0/1，不是 JSON true）。
- `5 gim_ctrl_speed_mode`：0–4 可写，**`Custom=100` 不被接受** ⇒ `CONSTRAINED`。
- `15/17 OffsetX/OffsetY`：在 **`GimCtrlMode=PRO` + Track + Composition** 前置下写入仍读到 `0.0` ⇒ `UNSUPPORTED_TAIL2`（与 M0.5 负结果一致，且现在有回读证据）。
- 其余（含限位 19–22、增益 7/10、锁 8/11、AutoZoom 12/13/23）均为 `READBACK_VERIFIED`，全部已还原。
- 行为/视觉效果需要移动目标 + 跟踪会话 ⇒ 交 Wave B。

## 4. A3 Target View / Zoom

- `aiSetTargetZoomTypeR`：**状态可回读** —— `ai_sub_mode` 映射 `−1/0→0`、`1→1`、`2→2`、`3→3`、`4/5/6/99→4`（Human Normal/FullBody/HalfBody/CloseUp/CustomAutoZoom）。
  但 **full-body 与 close-up 的画面几乎完全一致**（640×480，2 次）⇒ 视觉效果 `ACCEPTED_UNPROVEN`（bbox scale/cx/cy 未插桩）。
- `aiSetTargetViewTypeR`：12 个文档值全部 `rc=0`，`ai_sub_mode` 与 zoom **毫无变化** ⇒ 无效果（`ACCEPTED_UNPROVEN`）。
- 无 `aiGetTargetZoomTypeR` / `aiGetTargetViewTypeR` ⇒ framing 数值回读 `NO_PUBLIC_PATH`，只能读 `ai_sub_mode`。

## 5. A4 Zoom family

- `cameraSetZoomAbsoluteR`：`VERIFIED`，但**是慢速异步斜坡**（speed=5 时 1.0→1.11 用 ~5s，约 0.025/s），getter 滞后。
- `cameraGetZoomAbsoluteR` 归一化 ≥1.0；`cameraGetRangeZoomAbsoluteR` 返回 `{0,100,1,0,valid}` —— **单位空间与归一化回读不一致**（未解）。
- **`cameraSetZoomStopR`、`cameraSetZoomWithSpeedRelativeR`、`cameraSetZoomWithSpeedAbsoluteR` 在 Tail2 上均为 `UNSUPPORTED_TAIL2`（fw 7.2.9.41 实测无效果，且未找到任何可用条件）**：rc=0，但 zoom 不动/停不住（stop 后仍 1.10→1.15→1.23）。
- `aiSetAiAutoZoomR`：rc=0，无回读、无隔离视觉 ⇒ `ACCEPTED_UNPROVEN`。
- 数字变焦：只有枚举，无 setter ⇒ `NO_PUBLIC_PATH`。

## 6. 对中间层的影响（本轮最重要的产出）

1. `Look` 不必再建立在 ±10 dps 限速 hack 上；可以做**绝对角度 + 原生停止**，但必须**显式管理 AI 所有权**（Track 中绝对控制会被争用）。
2. **rc=0 无效果这一类静默失败必须用「期望效果判据（Expected Effect Predicate）」兜住**：`view.set` / zoom stop / zoom relative / zoom with-speed 在本轮测试前置下都 rc=0 且无效果。
   **不做通用 no-op 检测器**（`rc==0 && getter 未变 => no-op` 会制造新的假判定）；每类能力用各自的判据（offset→typed readback、zoom→时间序列、zoom stop→斜率收敛、gimbal→角度/角速度、lock→响应被抑制、framing→frame-bound bbox、gesture→事件+状态+物理响应），证据不足只能记 `ACCEPTED_UNPROVEN`。
3. **文档适用性不可信**（两向都已被证伪）；`docs/Tail2_SDK_CENSUS.md` 的 applicability 只能当线索。
4. framing 的**唯一回读通道是 `ai_sub_mode`**；构图数值域在 Tail2 上不可读，构图原语只能表达「状态」，不能表达「精确值」。

## 7. 纪律与恢复

- 每次写都走 `PRE-STATE → GET ORIGINAL → ONE WRITE → rc → READBACK → 视觉/物理 → 副作用 → RESTORE → POST-STATE`。
- 架构级结论（绝对 Look）重复 3 次；其余关键结论 2 次。
- 每项实验后均还原并复读；结束时设备为 `ai_main_mode=0`、`ai_sub_mode=0`、zoom 1.0、云台 0/0、参数默认、target 已清。
- 未执行任何 destructive API；未删改用户预置（本机预置列表为空）。
- 构建前先停掉本机残留的旧 probe 进程（占用 exe 导致 LNK1104），未影响设备。

## 8. 建议的下一步（Wave B 输入）

1. 在移动目标下验证 A2 的行为效果（Composition / PanLocked / GimCtrlMode=PRO / gains）。
2. `aiSetGimbalParaR` 写入（限位 / PanReverse / PresetSpeed）带还原；`aiTrgGimbalBootPosR`。
3. 手势家族与 Agent 所有权的冲突（Wave B1）。
4. 对焦 / 白平衡是否值得进入相机原语，还是留在 adapter 策略（Wave B2）。
5. 状态回调 / 热插拔是否能把轮询换成事件（Wave B4）。
6. Sample 引用暴露出的 46 个尚未完成 truth 定级的符号按价值分流：LimitedZoneTrack / `aiSetTrackingModeR` / `aiSetZoneTrackGimbalEnabledR` 优先进入 Wave B；FaceFocus / WDR / WhiteBalance 进入 IQ；网络 getter 等低相关项进入 Wave D/NOT_PRODUCT_RELEVANT 评估。
