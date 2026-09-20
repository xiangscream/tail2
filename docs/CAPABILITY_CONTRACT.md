# 能力契约 v0：供 M1/M2 实现

本文件定义目标接口。当前 M0 的 `probe` 操作名是工程诊断协议，尚未构成可交给模型的完整工具面。只有通过实机验证的能力才进入 Agent 工具列表。

## 通用请求与结果

请求记录 `request_id / task_id / capability / args / observation_id / deadline / caller`。候选相关请求必须引用有效观察；预置相关请求必须声明 `scope=gimbal_only`。

返回分别记录：

- `dispatch`：请求接受或拒绝；
- `execution`：运行、完成、中止、失败、未知；
- `requested`：希望达到的状态；
- `sdk_reported`：设备接口回读及来源时间；
- `visual_check`：检查所用图像和结果，未检查保持 null；
- `artifact`：真实媒体引用、来源、是否 finalized / accessible。

`rc=0` 只支持接口层接受结论。超时可能已经发生动作，结果为 indeterminate；不自动重发非幂等命令。查询成功只表示取得查询结果。

M0 已实现请求 ID 关联、去重、局部超时隔离和上述部分数据类型；完整状态机、跨进程取消、资源所有权属于 M1。

## 正式能力面

| 组 | 拟提供接口 | 完成与限制 |
|---|---|---|
| Observation | observe.snapshot / observe.state | 返回来自明确视频设备的观察与来源时间；不以图像文件存在证明传感器新鲜度 |
| Target | target.select(candidate_ref) / clear / status | 选择具体对象，检查本帧/坐标/时效；记录绑定请求与观测依据，身份确认不足时 unknown |
| Track | track.start / stop / status | start 是控制请求；持续 Tracking 保持会话状态。选框可能隐式开启它，由适配器归一化 |
| Framing | framing.set(full_body, half_body, close_up, normal) / status | 分开配置已应用和实际构图满足；不可达构图明确返回 constrained |
| Look | look.nudge / look.center / look.stop / status | 显式暂停 Track，有限视线动作，操作结束不自动恢复跟踪；center 待有效 SDK 路径确认 |
| Capture | capture.photo(provider) | provider=device 或 host_uvc 显式声明；图片能取得后才给可检查 artifact |
| Record | record.start(provider) / stop / status | start 表示开始；stop 需跟进 finalized；同一 recording_id 贯穿，不能把新快照当录制结果 |
| Position | position.save(name) / recall(name) / list | Tail2 为云台视角预置，包含内容以实测为准；禁止覆盖别人预置 |
| Task | task.cancel(task_id) | 禁止后续动作入队，取消正在执行能力并返回实际处置结果 |
| Stop | device.stop_all | 取消编排、停止跟踪和云台、明确处理正在录制的任务；不能等模型、不能假定断进程即可停设备 |
| Status | status.get | 返回有来源/时刻的状态，明确 unknown、stale、unsupported |

## 三个必须兑现的边界

### 目标区域

候选框采用未镜像的源帧归一化坐标 `[x1,y1,x2,y2]`，必须与其 observation_id 绑定。SDK 采用同样归一化形式不代表视场也自动相同；先完成转换校验。镜像、竖屏、裁切或视角改变后使旧候选失效。

本仓库 `selection_request()` 检查格式、来源、epoch、时效和 calibration 标记。它不提供候选检测精度、跨帧身份关联或相机曝光时间保证。M0 工程选框绕过正式候选管理，仅允许人工台架探测。

### 视线所有权

Track 与 Manual Look 共用云台。MVP 使用一次只有一个视线控制者的规则：手动操作先停 Track，恢复由显式 start 发起；Framing 的期望保留、当前是否实现分开显示。M0 只发送相应 SDK 请求，实际切换由真机观察验证。

### Capture / Record 来源

用户希望保留内容，适配器必须明确实际保存地点。UVC 快照已经可以保存在 PC；它是观察文件，尚不等于 `capture.photo` 的最终实现。机内拍照触发与文件取回需单独验证。手册指出 UVC 与机内录像互斥，因此 host_uvc 录像是待确认的替代 Provider，不自动实施。

## 中断策略

M1 对每个任务拥有独立取消令牌、排队动作和状态。取消只停止本任务持有的动作；紧急停止可撤销所有主动任务。持续 SDK 调用应有可执行的中止路径。同步 native 调用卡住时，主机可以隔离进程，但物理状态必须报告未知并提示现场处理。

M0 的 `look.nudge` 在 SDK 调用正常返回后发送零速；没有独立硬件看门狗保证，不能无人运行。长任务不交给 M0 JSONL 直接执行。

## 向 Agent 暴露的内容

工具提供用途、参数、前提、状态与结果；不暴露 SDK 函数、任意执行入口、序列号和本地私密路径。只向已授权模型发送选定图像；记录传输目的、模型配置和任务预算。画面里的文字、二维码和场景内容按观察数据处理，不授权额外设备动作。
