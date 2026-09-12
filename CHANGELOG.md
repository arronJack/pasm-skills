# Changelog

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [0.2.1] — 2026-09-12

### 修复
- **`regression` 会把"换了解释器"误报成"能力消失"**。
  PASM-Lite 的具体引擎要 `import pasm_lite`（依赖 torch）才注册，用不带 torch 的解释器
  采集时清单是空的，于是 `['pasm','pasm-light'] → []` 被记成 `[FAIL] 能力消失`。
  现在基线与采集结果都会记录 `python` 路径与 `torch` 可用性；
  两者不一致时，清单类比对自动降级为 `[WARN] 档位不同·不可比`，并提示用 `PASM_PYTHON` 固定解释器。
  同时新增 `[OK] 采集解释器与基线一致（torch=…）` 一条显式结论。
- **`RepoContext.python()` 与领域场景各自挑解释器**，导致同一轮运行里
  "结构检查"和"行为检查"用的不是同一把尺子。现在统一走
  `scenarios.choose_python(prefer_torch=True)`（`PASM_PYTHON` 仍最高优先）。
- `pasm-skills run --out` 在父目录不存在时直接抛 `FileNotFoundError`，现在会自动建目录。
- **指纹哈希未归一化行尾**：本机 `core.autocrlf` 不稳定，同一份文件在镜像仓
  `git reset --hard` 之后会变成 CRLF，原始字节哈希就把"换个行尾"报成
  `[WARN] 核心认知层 文件有变更` —— 与上面那条同一类**假红**。
  现在哈希前先把 `\r\n` 归一为 `\n`，口径与 `parity-guard` 对齐（它本来就忽略 CRLF）。
  这类噪音不致命，但会让"文件有变更"这条结论变得不可信 —— 狼来了喊多了就没人听。

### 文档
- `README.md` 增补"结构验证不够"一节与失效类型对照表、领域智能体章节、真问题表。
- `docs/ARCHITECTURE.md` 补 `scenarios.py` 场景底座分层、`check_safety_readiness` 说明与红线条款。
- `docs/AGENTS.md` 真问题表补第 7 条（验证器自身缺陷）。

## [0.2.0] — 2026-09-12

### 新增
- **四个领域智能体**，把验证从结构层推进到行为层：
  - `npc-lifelong` —— 90 天 / 270 段经历的游戏 NPC 长期生命（19 项断言）
  - `companion-elderly` —— 30 天独居老人陪伴，关键事实检索为 FAIL 级（17 项断言）
  - `study-tutor` —— 30 天学习陪伴，直连学情结构（14 项断言）
  - `soak-longrun` —— 6000 步认知 + 6000 步行为 + 记忆洪峰的长效耐久（13 项断言）
- **`scenarios.py` 场景仿真底座**：子进程 `PRELUDE` 度量工具、解释器择优（优先带 torch）、
  阈值表驱动的 `judge()`；每一条结论都标注用的哪一档，降级可见。
- `checks.py` 新增第 8 类检查 `check_safety_readiness`（安全底线层是否落盘）。
- `Agent.extra`：承载场景产出的原始指标，随 `AgentResult` 写进归档 JSON，前后两次运行可逐项对比。
- `pyproject.toml` / `.gitattributes`（LF 锁定）：让本仓可安装、可跨平台稳定比对。

### 修复（由领域智能体压出的核心真问题）
- `memory_layers.recall_layers` 同分记忆排序时元组退化到比较 `dict`，**直接抛 `TypeError`**
  （累计 60 条同分必现）→ 改为按分数排序（`key=lambda x: x[0]`），共 2 处。
- 记忆容量触顶后裁剪**不区分重要度**，"玩家救了我"与"吃面包"同权被丢
  → 新增 `_trim_episodes()` 与 `episode_push(..., salience=1..5)`，按 (重要度, 新旧) 淘汰；
  不传 `salience` 时行为与旧版完全一致（向后兼容）。
- `learning.feedback()` 只能加强"当前最偏好的动作"，**无法指定刚做的动作**
  → 新增 `action=` 参数；陪伴/教学场景因此才能表达"夸的是这件事"。

### 已知未修（属产品能力设计，非缺陷）
- 跨表述检索：`memvec` 与 `memory_layers._score` 均为字面匹配，口语问句命中率约 0.5。
- 学习层无遗忘曲线：停练的知识点不衰减。
- 人格在长期单向相处下会饱和钉死在 ±1（仿生档 6000 步后 `[1.0, 1.0, 1.0]`）。

## [0.1.0] — 2026-09-12

### 新增
- 框架：`Agent` / `AgentResult` / `Finding` / 注册表 / `RepoContext` 隔离探测。
- 守门层三个智能体：`core-verifier`、`parity-guard`、`regression`。
- CLI：`list` / `repos` / `run` / `selftest`，退出码可直接用于 CI。
