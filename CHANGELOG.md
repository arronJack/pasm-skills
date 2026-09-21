# Changelog

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [0.6.2] — 2026-09-21

### 新增

- **`cognition/relevance.py` —— 相关性闸门**（"这条资料够不够格当依据"）。

  **为什么需要它**：语义检索对**任何**问题都会返回若干条结果（只是分数不同）。
  直接把弱命中当依据，会让「无依据必须拒答」形同虚设。实测：

  > 问「髋关节置换术后康复方案」→ 命中「过敏史·磺胺」(score 0.47) → 系统据此作答

  **为什么不能用分数阈值**：记忆打分带时间衰减（`0.6 + 0.4×recency`），
  用绝对阈值当"查不到"的判据，结果是**资料库越老、系统越"失忆"**；
  且真命中与假命中的分数区间重叠（真命中最低 6.00 / 假命中最高 2.29），
  调不出一个稳的阈值。

  所以闸门用**与分数无关的结构判据**：命中的词必须落在资料的
  **标题或标签**上（正文里的偶然词重合不算 —— 标题/标签是人有意打的语义标记）。

  接口：`tokens` / `surface_of` / `touches` / `overlap` / `select_evidence`。
  `select_evidence` 返回空列表是**有意义的结论**：没有能支撑回答的资料 → 调用方应拒答。

  这是**共享实现**：`pasm-customer-service` 与 `pasm-medical` 都用它，
  不再各自维护一份（同源多份代码的行为漂移，这个生态已经吃过一次亏）。

## [0.6.1] — 2026-09-21

### 文档

- 更正 `cognition/capabilities.py` 的迁移状态说明：此前写成"MCP / HTTP 都转发到这里"，
  但 **`pasm-mcp-server` 目前仍是自己那份实现**，尚未委托。原表述与事实不符。

  **为什么值得单独发一个补丁版**：这段说明**在 wheel 里**。0.6.0 是先构建、后改文档，
  于是发出去的包带着一句不实陈述 —— 这是"产物时效性"问题的典型形态
  （源码已更正、产物仍旧）。包行为与 0.6.0 **完全一致**，仅文档差异。

## [0.6.0] — 2026-09-21

把认知能力从"只有 MCP 能调"提升为**基座级的共享实现**，让 HTTP / 桌面 / 脚本
等任意表面都能复用同一份逻辑。

### 新增

- **`pasm_skills.cognition.capabilities`** —— 认知能力门面（surface-agnostic）：
  - `Capabilities`：13 个操作（`context` / `recall` / `semantic` / `focus` /
    `status` / `observe` / `feel` / `act` / `feedback` / `consolidate` /
    `chat` / `persona` / `save`），全部返回可直接 JSON 序列化的纯 dict。
  - `AgentRegistry`：按 `agent_id` 管理实例，同 id 共享记忆 / 情绪 / 动作权重。
  - `CapabilityAgent`：通用认知智能体（动作池 / 人格 / 渲染可配置）。
  - **为什么收敛到基座**：这套语义此前只在 MCP 侧实现。当 HTTP 表面也要用时，
    照抄一份就会产生**同源两份代码** —— 而本项目已经因为同源两份代码出过真实缺陷
    （相关性闸门只回植了一边）。放在共同祖先层，两个表面都只是薄适配。
- `tools/falsify_capabilities.py`：反例对照脚本。**"19 项全绿"不算数** ——
  必须故意改坏还能被抓住。首次运行就抓出一条**假绿断言**：隔离检查原先写成
  "两边互不包含"，注册表整体坏掉、两边都返回空列表时**照样通过**。

### 修复

- **`persona` 更新重启即丢**。基座 `BaseAgent._load_state` 刻意让 persona 以构造入参
  为准（产品智能体的人格写在代码里，这是合理的）；但对**提供 persona 写入接口**的
  表面就是名不副实：用户调了设置、看到成功，重启却变回默认值。
  在 `AgentRegistry.get()` 里补上落盘读取（构造入参 > 上次落盘 > 默认），
  **不动 BaseAgent**，因此不影响已发布的产品智能体。

## [0.5.2] — 2026-09-20

### 修复

- **技能包构建：`clean_dist` 漏清根目录 ZIP**
  它只把 `zip-root/` 与 `slug-dir/` 两个**目录**挪进 `_stale/`，
  根目录下的上传用 ZIP（`<name>-<ver>.zip`）却原样留下 —— 新旧版本混在同一目录，
  上传时极易拿错文件，是"发出去的还是上一版"的经典成因。
  现在根目录 `*.zip` 会一并挪到 `_stale/zips-<时间戳>/`。

## [0.5.1] — 2026-09-20

### 变更 —— 应用框架独立成仓

- 移除 `pasm_skills/framework` 子包，应用层（`BaseApplication` / `BaseSkill` /
  `CapabilityDiscovery` / `DomainAdapter` / `CognitiveAssembler` / `CognitiveService` 等）
  迁至独立仓 **pasm-framework**（`pip install pasm-framework`）。
- 基座只保留引擎接线与 SDK：`BaseAgent`、`pasm_skills.sdk.backend` 的
  `CognitiveBackend` 协议（**单一真相源仍在基座**）、`create_v1_backend` 等。
- 依赖方向收敛为单向：`pasm-agents` → `pasm-framework` → `pasm-skills` → 引擎。
  基座不再 import 任何应用层内容。

## [0.5.0] — 2026-09-15

### 新增 —— 认知能力层 `pasm_skills.cognition`（补齐四项长期短板）

新增子包，零第三方依赖、档位无关、旁挂式接入（`enhance(agent)` 两行接入，不改 `BaseAgent`）：

| 能力 | 长期的真实问题 | 模块 |
|---|---|---|
| 语义检索 | 记忆存「姓名」、用户问「我叫什么名字」→ 字面匹配命中率约 0.5 | `cognition/semantic.py` |
| 遗忘曲线 | 停练 25 天与昨天一样强 → 学情失真、检索噪声累积 | `cognition/forgetting.py` |
| 记忆巩固 | 只有进没有蒸馏 → 重复经历撑爆记忆池 | `cognition/forgetting.py` |
| 焦点栈 | 长对话跑题、不知道"现在在聊什么" | `cognition/focus.py` |
| 心跳主循环 | 智能体纯被动，无空闲自主行为、无后台任务时机 | `cognition/tick.py` |
| 工具注册表 | 动作名 ≠ 可执行工具；无法被发现、无法被授权 | `cognition/tools.py` |

关键设计：

- **可插拔向量后端**：内置 `hashing-ngram`（零依赖离线保底），装了 sentence-transformers /
  fastembed 或配了 `PASM_EMBED_URL` 就自动接管，索引结构不变。
- **中文同义扩展桥**：命中概念（姓名/年龄/薄弱/情绪…）就扩展同义说法检索 —— 这是"换说法命中率"的真正来源。
- **旁挂 sidecar 而非改写主存储**：复习次数 / 已合并 / 已归档记在 sidecar 文件里，
  核心档与轻量档共用一套逻辑，不破坏任何一方数据。
- **异常隔离**：心跳处理器炸了循环照常；单个工具炸了不影响智能体。
- **间接索引**：`SemanticIndex.similarity(key_a, key_b)` 直接读向量，
  避免巩固聚类退化成 O(n³)。

### 变更

- CLI 新增 `pasm-skills cognition`（认知层自检，27 项）。
- `packages` 纳入 `pasm_skills.cognition`。
- **运行时版本号对齐**：`pasm_skills.__version__` 此前停在 `0.4.4`，与 `pyproject` 的
  `0.5.0` 不一致 —— `pip show pasm-skills` 与 `import pasm_skills` 会报两个版本，
  上游按版本判断能力是否存在时会误判。现已对齐（`0.4.3` 修过一次同样的漂移）。

### 验证

- `python -m pasm_skills cognition` → **27 项通过，0 失败**（含端到端：换说法命中身份记忆、
  复习效应、巩固落盘、重启后索引恢复、零第三方依赖静态检查）。
- `python -m pasm_skills selftest` → 通过（框架未改坏）。
- 版本号对账：`pyproject` 0.5.0 == `pasm_skills.__version__` 0.5.0。

## [0.4.4] — 2026-09-14

### 新增 —— 记忆质量评测（`check_memory_quality`）：把记忆层从「零覆盖」变成可回归基线

- **问题**：`core-verifier` 对**记忆层**只做结构体检，没有任何行为断言 —— 而记忆恰是本项目的核心卖点。
  更隐蔽的是「零覆盖」的结构性根因：校验套件探测的是模块里有没有 `selftest()` **可调用对象**，
  而只写 `if __name__ == "__main__"` 的自检 = **探测为空 = 零覆盖**（模块看着有自检，套件眼里不存在）。
- 新增 `checks.py::check_memory_quality`：**16 条行为断言**（不是"文件存不存在"），覆盖情景记忆固化、
  显著度排序、遗忘曲线、**只巩固真被召回进上下文的条目**、去抖落盘、双时态事实（矛盾 → 旧事实失效而非删除）、
  意图别名命中、世界模型后验与冷启动先验等。
- `CORE_COGNITIVE_MODULES` 纳入 `facts` / `worldmodel`，认知层体检从 13 个文件扩到 **16 个**。

### 验证

- `python -m pasm_skills run --all` → 0 fail；记忆质量 16/16。
- 该检查接入 `all_checks`，`core-verifier` 自动带上，无需改调用点。

## [0.4.3] — 2026-09-14

### 修复 —— 核心档（`use_core=True`，即装了私有 PASM 核心时）的反馈塑形与召回

- `sdk/base.py` 的 `_CoreAdapter.recall` 原来调 `recall_layers(..., k=k)`，但核心函数
  的关键字参数是 `top` 不是 `k` → `TypeError` 被 `except` 吞掉 → **核心档召回永远返回空**。
  改为直接用核心的 `episodes()` + `_score` 取情景记忆 dict（契约与 `_LightAdapter.recall` 一致），
  顺便修掉"返回字符串被逐字符遍历成一堆 `{'content':'某字'}`"的旧坑。
- 顺手修正 `__version__`（此前 `pyproject` 已是 0.4.2 但 `__init__` 还停在 0.4.1，运行时版本号对不上）。
- 注：核心 `LearningEngine.design` 的 `STAGE_ACTS` 过度裁剪问题在私有核心
  `pasm/cognitive/learning.py` 修（详见 PASM 核心仓），本仓 SDK 无需改设计逻辑。

### 验证

- 核心档反馈塑形：teach 23.8% → 80.0%、peek 29.5% → 3.5%（此前锁死在 peek）
- 核心档召回：`recall('行程问题')` 正确命中 title，chat 能引用该记忆
- light 档（公开用户默认）无回归：`python -m demo.run_all` / `pasm_skills selftest` 全过

## [0.4.2] — 2026-09-13

### 新增 —— `demo/` 分步教程包：手把手教人从零写一个智能体

此前基座只有单文件 `examples/build_your_agent.py` 和长文档，缺一个**结构化的「分步 demo 包」**：
照着它，新人能在 30 分钟内写出第一个会记忆 / 有情绪 / 能被反馈塑形 / 能落盘的智能体，
并知道**写出来之后怎么接进真实产品**、看到**真实跑出来的应用效果**。

`demo/` 内容（每个 step 独立可跑，文件即课时）：

| 文件 | 讲什么 |
|---|---|
| `README.md` | 分步实现（1→6）+ 应用（CLI / FastAPI / 游戏）+ **真实效果对照表** |
| `agent.py` | 完整版「学习陪伴·小墨」：6 步演变后的最终形态（可直接 `import` 用） |
| `step_01_minimal.py` | 最小智能体（只写 `action_pool` + `_render_reply` 两个钩子） |
| `step_02_memory.py` | + 记忆（重要度 `salience` 决定淘汰） |
| `step_03_feedback.py` | + 反馈塑形（`feedback(kind, action=)`，行为被学习改变） |
| `step_04_emotion.py` | + 情绪（`mood` 属性影响语气） |
| `step_05_state.py` | + 结构化学情（`state.notes` + `snapshot()` 机读出口） |
| `step_06_growth.py` | + 成长（`growth_stage` 解锁动作池） |
| `step_07_apply.py` | 应用：真实对话 + 跨进程恢复 + 3 种集成骨架 |
| `run_all.py` | 一键跑完 6 步 + 汇总应用效果 |

设计要点（与基座契约一致，均实跑验证）：

- 演示主角「小墨」复用 `BaseAgent` 全部能力，**不引入任何新 API**——教的是基座本身怎么用；
- 反馈塑形表用 `seed=0` 可复现：`teach` 28.2% → **100%**、`peek` 23.2% → **0%**；
  并如实说明这是 softmax 饱和（夸一个动作会让它主导），想保留多样性就分散夸多个动作；
- `light` 档（无核心）下全部跑通，且 `tier` 如实标注——降级永不隐藏。

运行：`python -m demo.run_all`（从仓根）或 `python demo/step_01_minimal.py`。

### 修复

- `demo` 包钉死在 SDK 内置 `light` 档（`demo/__init__.py` 在 import 时把 `BaseAgent.__init__`
  的 `use_core` 默认值改成 `False`）：本机装有私有 PASM 核心时，demo 默认会走 `core` 档，
  而当前核心的反馈塑形 / 记忆检索尚有缺陷，会让教程「应用效果」数字失真
  （如 `recall('行程问题')` 返回空、反馈前后动作分布不变）。钉死后教程在**任何环境**都显示
  确定且正确的效果，也契合「离线优先、不依赖私有核心」的设计。

### 变更

- README 目录补 `demo/`，「30 秒写一个智能体」一节加 `demo` 包入口
- 版本 0.4.2（与 `pasm-agents` 对齐到 0.4.3）
- `demo/README.md` 新增「PASM 是什么 · 为什么用 pasm-skills · 优劣势」前置章节：
  含三层交付关系、核心特性表、与"从零写 / 纯 LLM / 编排框架"的对比、优劣势与适用边界、一句话选型

## [0.4.1] — 2026-09-12

### 新增 —— CLI 报"未知智能体"时给自救指引（`_missing()`）

`python -m pasm_skills run <名字>` 原本只有一行 `[FAIL] 未知智能体 x`，用户看不出发生了什么。
现在分两种情况给出路：

- **发现 0 个**：直接点明"你只装了基座"（并说明这是刻意设计、不是你装错了）+ 装什么
- **发现 N 个**：列出可用清单，并用 `difflib` 给**近似建议**（`core-verifer` → `core-verifier`）

动机：拆仓后外部平台上**已发布的旧技能**（ClawHub，33 次下载）指向的是基座仓，
那些人照旧文档跑就会撞上"未知智能体"。这条提示让他们**不用回头查文档也能自己修好** ——
文档只能修新下载的人，运行时报错才能救到已经装上的人。

### 新增 —— `docs/TUTORIAL.md`：详细使用教程

基座的能力此前散在 README / BUILD-AGENT / SKILL-FORMAT 三份文档里，各有侧重但都不成体系。
新增一份**从零走到发布**的教程，11 节：

1. 心智模型（**基座不含智能体**这条最关键）/ 两条扩展轴 / 档位
2. 六十秒验证
3. 概念地图（persona / 动作池 / 记忆 / 反馈 / 档位 / 发现）
4. **路线 A：写产品智能体** —— 最小版本 → 记忆 → 反馈塑形 → 性格 → 情绪 → 结构化状态 → 初始记忆 → 方法速查
5. **路线 B：写验证智能体** —— 结构型 / 行为型 / 阈值表写法 / 三条红线
6. CLI 全参考（子命令 + `run` 参数 + 退出码）
7. 环境变量全参考（发现 / 仓定位 / 解释器，含优先级）
8. 打包与发布
9. **排查手册**（12 条症状 → 原因 → 处理）
10. 进阶（CI / 定时 / 回归比对 / 嵌进 FastAPI 或游戏循环）
11. 文件速查表

**教程里的代码都实跑过**（不是对着印象写的）：

- §4.1 最小智能体 → `tier=light`，`act()`/`chat()`/`save()` 正常
- §5.1 结构型验证智能体 → 经 `PASM_SKILLS_PATH` 加载后跑通（`[OK] API 快照可用 -- 66 个公开名`）
- §4.3 反馈塑形表 → `seed=0` 可复现重测：`light` 被夸动作 0.26→**1.00** / 被凶 0.26→**0.00**；
  `core` 0.27→**0.80** / 0.26→**0.03**（旧文档里那组数字是早先不定期测的，已换成可复现口径，
  并注明 `core` 带 ε-贪心探索所以不会压到 0/1 两端）

顺带把 `skill/SKILL.authoring.body.md` 里同一组数字同步为可复现口径。

### 变更

- README 顶部把教程放在第一位；文档目录补 `TUTORIAL.md`
- 版本 0.4.1（与 `pasm-agents` 0.4.1 对齐）

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
