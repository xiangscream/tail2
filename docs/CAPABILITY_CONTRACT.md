# 能力契约 v0.2：M0 回读后基线

本文件定义 M1/M2 使用的产品级接口。M0 `probe` 是工程诊断协议，不直接暴露给 Agent。只有真机链路通过的能力才能进入模型工具面。

## 1. 通用请求与结果

请求记录：

`request_id / task_id / capability / args / observation_id / deadline / caller`

返回分开记录：

- `dispatch`：accepted / rejected；
- `execution`：running / completed / cancelled / failed / indeterminate；
- `requested`：希望达到的状态；
- `sdk_reported`：设备接口最近一次有效回读、来源时间与 stale；
- `visual_check`：检查所用 Observation 与结论；
- `artifact`：真实媒体引用、provider、finalized / accessible；
- `errors`：查询失败、设备冲突、timeout 等。

`rc=0` 只表示 SDK 接受请求。非幂等操作 timeout 后结果保持 indeterminate，不自动重试。

## 2. Observation

### observe.snapshot()

返回一个 Observation：

- `observation_id`
- `stream_session`
- `camera_epoch`
- 图像尺寸与方向
- host received time
- source / backend
- calibration version
- candidate set（若当前 Provider 已运行）

M1 的 Observation Service 是 Tail2 UVC 的唯一读取者。Agent、候选检测、host_uvc 媒体和状态页消费同一条流。

host received time 不等于相机曝光时间。镜像、旋转、裁切、变焦、重连和 camera epoch 变化都会使旧坐标失效。

## 3. Candidate 与 Target

Candidate Provider 优先级：

1. `host_detector`：MVP 主 Provider；
2. `agent_box`：显式 fallback；
3. `native_candidates`：当前 SDK 没有可用正式接口，不进入关键路径。

Candidate 结构：

`candidate_id / observation_id / class / bbox / provider / confidence? / provider_metadata?`

candidate_id 只在当前 Observation / CandidateSet 内有效，不代表跨帧身份。

### target.select(candidate_ref)

选择画面里的具体对象。进入 SDK 前必须验证：

- observation 仍在 freshness window；
- camera_epoch 一致；
- calibration 已验证；
- bbox 合法；
- provider 受允许。

Tail2 adapter 把 Candidate bbox 转成 `aiSetSelectedTargetR(Box)` 所需 ROI。UVC → SDK ROI 转换必须经过 M0.5 实机标定。

选框是否会自动开启 Tracking 或改变 Zoom 是硬件副作用，M0.5 真机结果出来后由 adapter 归一化并写回状态。

### target.clear()

清除设备当前选定目标。Runtime 中保留的历史 candidate 立即失效。

## 4. Track

### track.start() / track.stop() / track.status()

Track 表示 Tail2 的持续目标跟随。

如果设备的 `target.select` 天然开启 Tracking，Runtime 仍保持 Target 与 Track 两个产品语义，并把设备副作用记录为 `sdk_reported.side_effects`。若无法实现“已选目标但不跟踪”，状态必须说明 provider limitation。

Track stop 的真机停止路径已通过首轮 M0；持续任务完成与一次 stop 请求接受仍然分开记录。

## 5. Framing

### framing.set(full_body | half_body | close_up | normal)

`requested` 记录用户期望构图。SDK 配置回读不代表视觉构图已经满足。

完成状态至少分：

- `applied`：SDK 接受配置；
- `visually_satisfied`：新的 Observation 满足目标；
- `constrained`：受视场、目标距离或设备能力限制；
- `unknown`：没有足够视觉结果。

M0.5 必须完成 Full / Half / Close 的真机闭环，之后才进入 Agent 工具面。

## 6. Look 与控制权

### look.nudge() / look.stop() / look.status()

MVP 使用单一 Look Owner：

- Tracking 持有 Look 时，Manual Look 先停止 Tracking；
- Manual Look 完成后不自动恢复 Tracking；
- 恢复需要显式 `track.start` 或重新选择目标。

首轮 M0 已验证有限 gimbal speed 和 stop 在当前 Tail2 固件可用。角度查询有间歇失败，因此 `look.status` 返回 last-good value、source time、age 和 stale；单次错误不会把角度改成 0。

## 7. Capture 与 Record

MVP 默认 Provider 为 **host_uvc**。

### capture.photo(provider=host_uvc)

从共享 UVC 流中取得请求发生之后的新帧，保存成持久 artifact。返回：

`media_id / provider=host_uvc / path_ref / captured_observation_id / finalized / accessible`

它与 `observe.snapshot` 的差别是持久结果与任务语义。不能把请求前的旧 Observation 复制成“新照片”。

### record.start(provider=host_uvc)

在共享 UVC 流上建立 recording session。首版只承诺视频，不承诺音频和最终产品编码规格。

### record.stop(recording_id)

停止写入并 flush / finalize，文件可打开后才 completed。主机退出或 writer close 出错时返回 failed / indeterminate。

device-native Capture / Record 保留为实验 Provider，当前不进入 Agent 默认工具面。

## 8. Position

### position.save / recall / list

Tail2 上的 Position 仅表示云台视角 Preset。当前设备列表为空，save 尚未获准真机测试，因此 M1 标为 `experimental/unsupported`，不阻塞 Target 主链。

未来确认 ID 所有权、创建、recall 与清理后再进入工具面。

## 9. Task / Stop

### task.cancel(task_id)

阻止本任务后续动作继续派发，并请求取消它拥有的持续能力。

### device.stop_all()

本地最高优先级停止：

- cancel 当前编排；
- stop Tracking；
- send zero gimbal speed；
- stop/finalize 活跃 host_uvc recording。

它不依赖模型返回。超时后设备物理状态保持 unknown，并提示现场检查。停止不自动清除历史 Target 语义；设备是否仍保留具体目标由状态回读决定。

## 10. Status

### status.get()

返回有来源时间的聚合状态，包括：

- device connection / readiness；
- target requested / sdk state / unknown；
- track state；
- framing requested / visual result；
- look owner 与 last-good gimbal attitude；
- media session；
- task state；
- stale / unsupported / provider limitation。

设备 discovery 使用 bounded polling + total timeout，不依赖固定 3 秒 sleep。只有显式 Tail2 UVC 设备进入 ready。

## 11. 状态页

页面只读、localhost、no-store。M1 可显示：

- 最新预览；
- Candidate boxes；
- requested target ROI；
- gimbal last-good angle + stale；
- Capability / SDK / Result timeline。

当前没有 native tracking bbox，页面不得把 Candidate 或 requested ROI 标成设备实时跟踪框。真实图像不写公开 trace。

## 12. 向 Agent 暴露的内容

Agent 只看到正式能力、当前状态、允许的 Observation 和结果。它看不到 SDK 函数、任意命令执行、序列号、本地私密路径和未验证的实验能力。

M2 的多模态 Agent 负责：看图、语义选候选、组织能力、根据视觉结果继续 / 重试 / 完成。Tail2 保持高频 Tracking / Gimbal 闭环。
