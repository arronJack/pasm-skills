# Changelog

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [0.4.0] — 2026-09-12

### 变更（破坏性）—— 本仓转为**纯基座**

v0.3.0 的本仓既当"框架"又当"成品智能体仓库"，定位混了：既想被人 `pip install` 当工具用，
又塞着三个面向使用者的智能体。这一版把两者拆开：

| | 现在在哪 | 内容 |
|---|---|---|
| **基座**（本仓 `pasm-skills`） | 这里 | SDK + 框架 + 场景仿真 + 打包工具 + 脚手架 + 文档 |
| **成品智能体**（新公开仓 `pasm-agents`） | 独立仓 | 3 个产品智能体 + 7 个验证智能体 + 4 个技能包 |

**移动清单**：

- `pasm_agents/{npc,companion,tutor,cli}.py` → `pasm-agents` 仓
- `pasm_agents/base.py` → **`pasm_skills/sdk/base.py`**（这是基座的核心，留在本仓）
- `pasm_skills/agents/*`（7 个验证智能体）→ `pasm-agents` 仓的 `pasm_agents/verifiers/`
- `skill/SKILL.{npc,companion,tutor,verify}.body.md` → `pasm-agents` 仓
- `baselines/`、`examples/*`、`docs/AGENTS.md` → `pasm-agents` 仓

**对你的影响**：

- `pip install pasm-skills` 仍然可用，但**不再自带任何智能体**；
  `from pasm_agents import NpcAgent` 请改 `pip install pasm-agents`。
- 本仓的 CLI 从 `pasm_skills` 改成 **`pasm-skills`**（原来那个名字与包名重复、还容易和智能体 CLR 混）。

### 新增 —— SDK 正式独立成层

- **`pasm_skills.sdk`**：`BaseAgent` 从"某个具体包里的实现细节"提升为**公开 SDK**。
  写智能体的人只需要实现两个钩子（`action_pool()` / `_render_reply()`），
  记忆淘汰 / 情绪 / 动作采样 / 反馈塑形 / 落盘全由 SDK 承担。
- `selftest` 扩到 **15 项**，新增 SDK 全链路自检：建 → 记忆 → 选动作 → 对话 → 反馈 →
  落盘（**不依赖任何 PASM 仓、也不依赖任何具体智能体**）。

### 新增 —— 智能体发现机制（基座不内置智能体）

`pasm_skills/discovery.py`，按优先级三道：

1. `PASM_SKILLS_PATH`（本地开发：指向文件或目录）
2. `PASM_SKILLS_AGENT_MODULES`（显式钉死模块名）
3. **entry points**（组名 `pasm_skills.agents`；装成包后自动发现）

三道都失败也**不报错** —— 基座照样能 `selftest` / `list`，只是智能体数为 0。
新增 `pasm-skills agents` 子命令：打印每个智能体是从哪加载进来的（排障用）。

### 新增 —— 打包能力提升为库

- `tools/build_skill.py` 里的规则下沉到 **`pasm_skills/build.py`**（`ProjectMeta` /
  `SkillSpec` / `build_all` / `run_cli`）。各智能体仓只需声明"我有哪些技能"，
  归档规则（含那个踩过坑的 ZIP 结构自检）集中一处，不再各抄一份。
- `author` / `homepage` / `repository` / `requires` 全部参数化（原来写死在本仓）。

### 新增 —— 脚手架与文档（"别人下载了能做出自己的智能体"）

- `templates/agent_template.py`：智能体骨架，复制即用，自带冒烟
- `templates/SKILL.template.body.md`：技能正文模板（含"已知短板"这类必填节的提醒）
- `examples/build_your_agent.py`：8 个环节的完整走查（含反馈塑形的实测对比）
- **`docs/BUILD-AGENT.md`**：手把手从零到发版（含检查清单）
- **`docs/SKILL-FORMAT.md`**：技能包格式、两种归档形态、frontmatter 逐字段说明
- 本仓自己的技能：`pasm-agent-authoring`（教人怎么写智能体 + 打技能包）

### 修复

- `sdk/base.py` 里 `_fallback_weights()` 的注释提到"子类可扩展 `ACT_BIAS`"——
  **这个属性根本不存在**，照它写会静默失败。已改为如实说明：要么动作名带关键词，
  要么覆盖整个方法。

验证：`python -m pasm_skills selftest` → 15/15 通过；
`python examples/build_your_agent.py` 与 `python templates/agent_template.py` 全跑通；
`python tools/build_skill.py --zip --clean` 产出 `pasm-agent-authoring-0.4.0.zip`（内含且仅含 `SKILL.md`）。

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

### 新增 —— 发布物（三个智能体各自独立成包）

- **产品层拆成三个独立技能包**，各自一份正文、各自一个 ZIP —— 按需只装一个：
  - `pasm-npc`（`skill/SKILL.npc.body.md`）
  - `pasm-companion`（`skill/SKILL.companion.body.md`）
  - `pasm-tutor`（`skill/SKILL.tutor.body.md`）
  - 原先的合集正文 `SKILL.agents.body.md` 随之移除（内容已拆进上面三份）
- `tools/build_skill.py` 重构：**一个正文 → 两种归档形态**，形态按**归档结构**命名，不按平台名
  - `zip-root`：`SKILL.md` 直接躺在 ZIP 根目录（实测：包成 `skills/<name>/SKILL.md` 会被拒收）
  - `slug-dir`：以 slug 命名的目录，目录里放 `SKILL.md`
  - 支持多技能（`--name` 只构建一个）、`--zip` 顺带打 ZIP 并内置结构校验
- 技能清单共 4 项：`pasm-npc` / `pasm-companion` / `pasm-tutor` / `pasm-longterm-verify`（v0.3.0）

### 修复 —— 产品层自身的 4 个真 bug（写技能文档时逐条实跑压出来的）

这四个都不是"效果差一点"，而是**功能根本没生效**，且失败得毫无痕迹：

1. **`_CoreAdapter` 参数名写错 → 核心档从未启用过**。
   `LearningEngine` 的参数是 `data_path`，代码写的是 `data_dir`，构造时 `TypeError`
   被 `except Exception` 静默吞掉 → `_core_ok=False`。**结果：装了 PASM 核心也永远跑轻量档**，
   "驱动 PASM 真核心"这句话当时是假的。
2. **`_CoreAdapter.learn_pick(candidates)` 把候选池当成了 epsilon**。
   `LearningEngine.pick(epsilon=0.15)` 收的是探索率，传 list 直接
   `TypeError: '<' not supported between 'float' and 'list'`，又被吞掉 → 退化成只有性格。
   而且 `design()` 从未被调用，学习层连动作池都不认识。
3. **`BaseAgent.act()` / `feedback()` 被 `_core_ok` 门挡住** → 轻量档下
   "反馈"只写进历史、**永不影响行为**；而轻量档正是 `pip install pasm-skills` 的默认路径。
   现在两档走同一套语义：**性格基线（天生偏好）+ 学习权重（反馈塑形）**。
4. **`companion.py` 缺 `import random`** → 关键事实没命中时 `ElderlyCompanion.chat()`
   直接抛 `NameError`。老人问一句模板覆盖不到的话就崩，这在陪伴场景是不可接受的。

实测（400 次 act 采样，60 次 praise(hop) + 60 次 scold(wave)）：

| 档位 | `wave` 占比 | `hop` 占比 |
|---|---|---|
| `core`（修复后） | 0.31 → **0.04** | 0.36 → **0.84** |
| `light`（修复后） | 0.24 → **0.00** | 0.23 → **1.00** |

顺带补齐：
- `LearningTutor.mastery(topic)` / `LearningTutor.snapshot()` —— 之前掌握度只躺在
  `state.notes["knowledge_state"]` 里，外部要读等于把私有字典当接口用。
  现在有稳定的机读出口（`mastery` / `weakest` / `average` / `history_size` / `tier`），
  画像层接的是契约而不是内部结构。
- `pasm-agents run` 交互命令补齐：`grow` / `facts` / `report <知识点> <分数>` /
  `next` / `snapshot` / `help`（原先只有 `act` / `mood` / `observe` / `feedback`）。
  三份技能正文里承诺的命令，现在**逐条实跑验证过**。

> 这四条也说明一件事：**验证智能体目前只体检了 `pasm.cognitive` 核心，没体检 `pasm_agents` 产品层**。
> 产品层的 bug 是"写文档时逐条跑示例"压出来的，不是智能体抓到的。
> 下一批验证智能体应该覆盖产品层 —— 这是当前验证覆盖的真实缺口，如实记在这里。

### 变更 —— 公开仓不携带个人环境信息

- **移除硬编码的本机解释器路径**（`scenarios.py`）。改为按优先级择优：
  `PASM_TORCH_PYTHON` → `PASM_PYTHON` → **本机配置** → `sys.executable`
  → 仓库内 `.venv` / `venv` → `py` → `python3` → `python`。
  本机配置的查找顺序：`PASM_LOCAL_CONF` env → **`~/.pasm-skills/local.json`（推荐，仓库外）**
  → `<repo>/pasm-skills.local.json`（兼容，gitignore）。支持 `%%HOME%%` 占位。
  "带 torch 的那个解释器"本来就在仓库外，所以配置也放仓库外，而不是写死在代码里。
  （踩到的坑：环境变量 `APPDATA` 被改写时，Python 的 user site-packages 会指向别处，
  `C:/Python312` 的 torch 就"时有时无"——所以必须指定**自带 site-packages 的 venv**，
  别依赖 user site。）
- **回归基线不再记解释器绝对路径**，只记 `Python 版本号 + torch`（`baselines/core.json` 是入库文件，
  不该带个人机器路径；对别人也无参考价值，档位比对只需版本号）。
- **归档报告同样不再记绝对路径**：4 个领域智能体原先往 `extra` 里写 `"python": <完整路径>`，
  现在统一走 `scenarios.python_label()` 输出 `Python 3.13.14` 这种可移植描述
  （报告是会入库、会贴出去的产物，塞个人路径既泄露信息又无参考价值）。
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
