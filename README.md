# Tail2 Embodied Agent MVP

让能看画面的 Agent，通过清楚、可组合的产品能力操作 Tail2：选择画面中的具体目标，跟踪、构图、调整视线、记录，并查看真实结果。

本项目优先验证 **Observation / Target / Track / Framing / Look / Capture / Record / Position / Stop / Status**。应用商店、应用框架和产品 UI 暂不开发。状态页仅用于观察调用过程。

## 当前交付

**M0 工具与离线验证已提供；Windows + Tail2 真机验证待完成。** 尚未接入模型，尚未完成视觉 Agent 演示。

- C++ libdev JSONL 探测桥：明确设备选择、默认只读、逐调用记录返回码。
- Python USB/UVC 单次观察工具，以及可选的本地 HOG 人体候选框基线。
- 候选框、观察时效、坐标映射、请求与实际状态分离的可测试基础契约。
- 只读 localhost 状态页；显示探测请求、SDK 调用与设备回读。
- Windows 构建脚本、离线测试、CI 与本地 Agent 交接任务。

**当前发现：**SDK 有 Tail2 选框与媒体控制声明；原生候选列表尚未找到可用接口。手册 v1.0 限制 UVC 与机内录像同时工作，当前固件行为需实测。见 [SDK 核对](docs/SDK_FINDINGS.md)。

## 从这里开始

| 读者 | 入口 |
|---|---|
| 产品 / 架构 | [完整开发计划](docs/DEVELOPMENT_PLAN.md) |
| Runtime 开发 | [能力契约](docs/CAPABILITY_CONTRACT.md) |
| 本地真机执行者 | [当前交接](docs/handoff/CURRENT.md) → [M0 操作手册](docs/M0_RUNBOOK.md) |
| 审查者 | [已执行验证与限制](docs/VERIFICATION.md) |

## 快速运行

Python 3.11+；只做离线测试无需 SDK：

```sh
python -m unittest discover -s tests -v
python -m tail2_mvp status --trace .local/run --port 0
```

状态页监听 `127.0.0.1`，自动选择可用端口；初始页没有设备数据，明确显示 Agent 未接入。

Windows 真机路径需 Visual Studio C++ x64、CMake、Boost.JSON 头文件和自行获得的 SDK：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[vision]"
.\tools\build_windows.ps1 -SdkRoot 'C:\private\libdev_v2.1.0_8' -BoostRoot 'C:\deps\boost'
python -m tail2_mvp probe --bridge .\build\Release\tail2_probe.exe --trace .local/run
```

先只读枚举，再按操作手册选择设备、核对画面和坐标，最后显式开启控制。所有数值限幅均为可审查的台架设置，不是 Tail2 产品参数。

## 数据与协作

仓库公开。SDK、真实画面、人物图像、序列号、原始日志、密钥与模型凭据只存本地 `.local/` 或仓库外。禁止提交厂商头文件和二进制。没有附带 SDK 授权，使用者需自行取得合法访问权。

通过 Draft PR 与 `docs/handoff/` 协作。真机结果提交脱敏摘要，保留复现步骤与精确 commit。主分支合并需经过审查。
