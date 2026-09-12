# Changelog

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [0.3.0] — 2026-09-12

### 新增 —— 产品层 `pasm_agents`（本仓的主交付物）

之前的仓库只有"验证智能体"（给核心体检的质检工具），没有"能被装载使用的智能体"。
这一版把产品层补齐：**三个真智能体 + 一个 BaseAgent**。

- **`pasm_agents/base.py`** —— `BaseAgent`：观测 / 记忆 / 情绪 / 动作 / 反馈 / 持久化。
  - `observe(text, salience=1..5, tags=[...])` 写记忆（重要度参与容量淘汰）
  - `act()` 按人格权重 + 反馈微调后的权重选动作
  - `feedback(kind, action=...)` **可指定"夸的是哪个动作"**
  - `chat(text)` / `save()` / `summary()`；落盘 `~/.pasm-agents/<id>/`
  - `_CoreAdapter`：**优先驱动 PASM 真核心**（`memory_layers` / `learning` / `emotion`），
    拿不到才降级到内置轻量实现，并把 `tier` 字段如实暴露（`bionic` / `core` / `light`）
- **`pasm_agents/npc.py`** —— `NpcAgent`：游戏 NPC。性格（temper/energy/play）决定动作基线，
  记忆带重要度，长期相处会被反馈塑形；示例见 `examples/npc_quickstart.py`
- **`pasm_agents/companion.py`** —— `ElderlyCompanion`：老人陪伴。
  关键事实（用药 / 过敏 / 家人 / 本人）100% 直查；用药提醒；危机识别与升级（写入紧急记忆 + 返回升级信息）
- **`pasm_agents/tutor.py`** —— `LearningTutor`：学习陪伴。
  每个知识点 EMA 追踪掌握度、最弱优先选题、鼓励式对话；学情可直接被画像层消费
- **`pasm_agents/cli.py`** —— `pasm-agents` 命令行：`demo` / `run` / `list` / `inspect`
- `examples/` 三个 30 秒示例：`npc_quickstart.py` / `companion_quickstart.py` / `tutor_quickstart.py`

### 新增 —— 发布物（两种归档形态）

- `tools/build_skill.py` 重构：**一个正文 → 两种形态**，形态按**归档结构**命名，不按平台名
  - `zip-root`：`SKILL.md` 直接躺在 ZIP 根目录（实测：包成 `skills/<name>/SKILL.md` 会被拒收）
  - `slug-dir`：以 slug 命名的目录，目录里放 `SKILL.md`
  - 支持多技能（`--name` 只构建一个）、`--zip` 顺带打 ZIP 并内置结构校验
- `skill/SKILL.agents.body.md`：产品层技能正文（新增）
- 技能清单新增 `pasm-agents`（v0.3.0）

### 变更 —— 公开仓不携带个人环境信息

- **移除硬编码的本机解释器路径**（`scenarios.py`）。改为按优先级择优：
  `PASM_TORCH_PYTHON` → `PASM_PYTHON` → **本机配置 `pasm-skills.local.json`（gitignore）**
  → `sys.executable` → 仓库内 `.venv` / `venv` → `py` → `python3` → `python`。
  本机那个"带 torch 的解释器"往往在仓库外，所以走**已忽略的本机配置文件**而不是写死在代码里。
- **回归基线不再记解释器绝对路径**，只记 `Python 版本号 + torch`（`baselines/core.json` 是入库文件，
  不该带个人机器路径；对别人也无参考价值，档位比对只需版本号）。
- `README.md` 目录与发布章节改写：平台专名从项目文档移出，改按形态（`zip-root` / `slug-dir`）说明；
  补"本机配置"一节与档位优先级。
- `docs/PUBLISH.md`（平台专名 + 个人操作细节）**移出仓库**，只留在本机发布指南里，不随公开仓分发。
- `docs/ARCHITECTURE.md` / `docs/SERVER-NEEDS.md`：解释器候选链与定时方案改为中性表述。
- `CHANGELOG.md` 中一处"记录 python 路径"的描述同步为"记录版本号"。

### 修复
- 技能包名与文档不一致：README 里写作 `pasm-engine-audit`，实际包名是 `pasm-longterm-verify` —— 已统一。

## [0.2.1] — 2026-09-12

### 修复
- **`regression` 会把"换了解释器"误报成"能力消失"**。
  PASM-Lite 的具体引擎要 `import pasm_lite`（依赖 torch）才注册，用不带 torch 的解释器
  采集时清单是空的，于是 `['pasm','pasm-light'] → []` 被记成 `[FAIL] 能力消失`。
  现在基线与采集结果都会记录 `python` **版本号**与 `torch` 可用性；
  两者不一致时，清单类比对自动降级为 `[WARN] 档位不同·不可比`，并提示用 `PASM_PYTHON` 固定解释器。
  同时新增 `[OK] 采集解释器档位与基线一致（Python x.y.z, torch=…）` 一条显式结论。
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
