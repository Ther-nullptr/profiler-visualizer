# Profile Visualizer

[English](README.md) | [简体中文](README.zh-CN.md)

独立的 agent skill 与推理性能可视化工具。将实测 profile 和优化历史整理成图表，
区分可比基线、逐轮增量与累计收益，不把估算当成实测结果。

GitHub 仓库名为 **profiler-visualizer**；为兼容已有调用，skill 名称与安装目录
仍为 **profile-visualizer**。

## 功能

- PNG 优化历史图，并保留可编辑 SVG 和证据 manifest。
- 带优化说明的单轮 SVG 算子耗时分解。
- 明确的增量、累计及匹配精度对照。
- 质量/采用状态、优化覆盖矩阵与来源文件指纹。
- 可选的离线 HTML 视图；不需要模型权重、GPU 或推理引擎。

## 快速开始

需要 Python 3.10+，本地验证环境为 Linux/aarch64、Python 3.12。
PNG 导出需要 CairoSVG 和系统 Cairo 运行库；单轮 SVG 和可选 HTML 不依赖 CairoSVG。

```bash
git clone https://github.com/Ther-nullptr/profiler-visualizer.git profile-visualizer
cd profile-visualizer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/render_optimization_history.py examples/history.json --output-dir outputs/demo
```

示例使用**合成数据，不代表模型实测性能**。输出 PNG、SVG、Markdown 和 manifest，
文件名以时间戳开头，不同工作负载与测量批次分别出图。

校验输入或切换视图：

```bash
python scripts/render_optimization_history.py examples/history.json --validate-only
python scripts/render_optimization_history.py examples/history.json --format html --output-dir outputs/html
python scripts/render_profile_breakdown.py examples/profile.json --output-dir outputs/breakdown
```

`--format both` 同时生成 PNG 与 HTML；`--update-index` 额外更新 `dashboard.md`
和/或 `dashboard.html`，保留带时间戳的快照。
CairoSVG 无法加载时，需要先配置所在系统的 Cairo 运行库；不需要安装或更换 PyTorch。

## 作为 Skill 安装

仓库根目录就是 skill 目录，在当前 checkout 中执行：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PWD" "${CODEX_HOME:-$HOME/.codex}/skills/profile-visualizer"
```

已有同名安装时，先核对其位置；命令不会强制覆盖。下一轮 agent 对话继续使用
`$profile-visualizer`。脚本也可直接运行，不依赖 agent 或其它 skill。

## 文档与结构

| 路径 | 职责 |
|---|---|
| [SKILL.md](SKILL.md) | Agent 工作流程与证据约束 |
| [Breakdown 格式](references/input-schema.md) | 组件耗时输入与 SVG 导出 |
| [历史台账格式](references/optimization-history.md) | 配置、运行、对照关系及 PNG/HTML 输出 |
| `scripts/` | 输入校验、收益计算与渲染 |
| `assets/` | 可选 HTML 的样式与交互 |
| `examples/` | 小型、自包含的合成输入 |
| `tests/` | 计量口径、渲染、来源追溯与独立运行测试 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 开发与验证说明 |

缺少对照时显示待补测；累计收益必须有明确的原始基线测量，不能连乘历史加速比。
精度公平对照还要求公共配置已知且一致、公共优化覆盖相同。
原始 trace、视频和生成产物不进入 Git。

## 开发验证

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

测试不需要 GPU 或模型仓库。历史格式文档中另有可选浏览器检查，PNG 导出无需浏览器。

## 来源与许可

从 `AI-Infra-Auto-Driven-SKILLS/skills/profile-visualizer` 拆分，保留相关提交历史，
并记录来源与维护者要求的身份修正，详见 [PROVENANCE.md](PROVENANCE.md)。
源快照没有 LICENSE 文件，本次拆分不擅自新增或推定许可授权；项目许可待维护者明确。
