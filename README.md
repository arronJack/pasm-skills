# PASM Skills · 智能体工坊

> 把「对 PASM 核心内容的长期验证」做成**可重复运行的智能体**，
> 而不是每次靠人回忆"上次好像是对的"。

本仓是 PASM 项目矩阵的**验证与运维智能体**公开放置点。
它不参与 PASM 的运行时，也不产出任何模型能力；它只做一件事：
**持续地、自动地、留下证据地确认 PASM 核心还是好的。**

---

## 一、为什么要单独开一个仓

PASM 已经出现过三类真实事故，全都要靠"人记得去查"才能发现：

| 事故 | 症状 | 本仓如何守住 |
|---|---|---|
| 符号层/记忆路由只落在 Studio 桌面端，核心包 `pasm/cognitive/` 从未包含 | "团队和技能库全失效"，且久未察觉 | `parity-guard` 逐字比对两仓，核心有 Studio 缺 = FAIL |
| 打包配置漏了模块搜索根，`import` 静默失败 | 团队/数学脑/感知在发行版里实际全废 | `core-verifier` 走真实引擎契约校验，不靠"能启动就算好" |
| 改动后无人复核，能力悄悄回退 | 只有用户真机复检才会暴露 | `regression` 存事实指纹，下次运行自动比对 |

共同点：**都不需要"更聪明的判断"，只需要"有人每次都老老实实查一遍"。**
那就是智能体该干的活。

## 二、结构验证不够 —— 所以有了领域智能体

`core-verifier` 回答的是「**东西在不在、接线对不对**」。
但 PASM 想做的是「记得住、有情绪、会自己学的长期伴侣」——
这类能力**在文件列表里永远是"正常"的**，只有跑久了才现原形。

于是本仓把验证从**结构层**推到**行为层**：起一个场景、让核心组件真的跑几十天、
然后拿阈值表去卡它的表现。抓到的失效类型完全不同：

| 失效类型 | 结构检查能看到吗 | 谁能看到 |
|---|---|---|
| 模块缺失、契约不符、接线断开 | ✅ 能 | `core-verifier` / `parity-guard` |
| 跑久了记不住早期重要事件 | ❌ 看不到 | `npc-lifelong` |
| 容量满了把"救命恩人"当垃圾丢掉 | ❌ 看不到 | `npc-lifelong` |
| 情绪长时间漂出边界 / 一次跳变过大 | ❌ 看不到 | `npc-lifelong` / `companion-elderly` |
| 行为越跑越僵化（熵塌缩） | ❌ 看不到 | `npc-lifelong` / `soak-longrun` |
| 反馈学习不生效（夸了不改） | ❌ 看不到 | `npc-lifelong` |
| 人格被单向相处推到饱和后钉死 | ❌ 看不到 | `soak-longrun` |
| 老人用药/过敏这类关键事实检索不出来 | ❌ 看不到 | `companion-elderly` |
| 停练之后不遗忘（无遗忘曲线） | ❌ 看不到 | `study-tutor` |
| 六小时连续运行内存/耗时劣化 | ❌ 看不到 | `soak-longrun` |

**这就是"做几个智能体"的实际价值**：不是多几个检查项，而是**换一个维度看问题**。

## 三、零依赖设计（刻意的）

只用 Python 标准库。不需要 torch、不需要 GPU、不需要 API key、**不需要服务器**。

理由不是"图省事"：

- **断网/无显卡/无 token 也要能跑** —— 验证器一旦有依赖，就会在关键时刻跑不起来；
- **结论只由代码事实决定** —— 不引入 LLM 的不确定性，避免"AI 说没问题"式的假安全感；
- **任何机器、任何时间、可重复** —— 今天和三个月后跑出的结论必须能直接对比。

需要"会思考"的智能体时，在 `run()` 里自己调 LLM 即可，框架不拦、也不强制。

**唯一的可选依赖是 torch**：装了，领域智能体就用**仿生档**（真实脉冲神经元 + 人格模块）跑；
没装，自动**降级到轻量档** `pasm.light.PASMAgent` —— 且**每条结论都会标注用的哪一档**，
绝不悄悄换成"看起来也在跑"的东西。降级是明说的，不是隐藏的。

## 四、快速开始

```bash
cd pasm-skills

# 1) 看环境：三仓定位 + 智能体清单
python -m pasm_skills list

# 2) 给核心做一次全量体检（结构层）
python -m pasm_skills run core-verifier

# 3) 跑领域智能体（行为层）
python -m pasm_skills run npc-lifelong
python -m pasm_skills run companion-elderly
python -m pasm_skills run study-tutor
python -m pasm_skills run soak-longrun          # 约 1~2 分钟

# 4) 存一次"事实基线"（此后任何退化都会被自动抓到）
python -m pasm_skills run regression --update

# 5) 跑全部
python -m pasm_skills run --all
```

Python 3.10+。仓库路径默认按约定查找（`E:/AI/PASM`、`E:/AI/pasm_qclaw`、`E:/AI/PASM_LITE`），
也可用环境变量显式指定：

```bash
export PASM_CORE=/path/to/PASM
export PASM_STUDIO=/path/to/pasm_qclaw
export PASM_LITE=/path/to/PASM_LITE
export PASM_PYTHON=/path/to/python        # 用哪个解释器做探测（默认当前解释器）
export PASM_TORCH_PYTHON=/path/to/python  # 指定"带 torch"的解释器，优先用于仿生档
```

## 五、内置智能体

### 5.1 守门层（结构验证）

| 名字 | 作用 | 需要仓库 |
|---|---|---|
| `core-verifier` | 全量体检：引擎契约 / 认知层是否真落盘 / 符号闭环接线 / 学习层两档 / 环境插件 / **安全底线** / 端到端冒烟 | core |
| `parity-guard` | 核心仓 ↔ Studio 仓 `pasm/cognitive/` 逐字一致守门 | core, studio |
| `regression` | 采集事实指纹，与基线比对，抓静默退化 | core |

### 5.2 领域智能体（行为验证）

| 名字 | 场景 | 断言数 | 关心什么 |
|---|---|---|---|
| `npc-lifelong` | 游戏 NPC 90 天 × 3 件事 = 270 段经历 | 19 | 长期记忆会不会丢、重要度淘汰是否生效、情绪会不会漂出去、行为会不会僵死、被夸/被训是否真的改变偏好 |
| `companion-elderly` | 独居老人陈秀兰 78 岁 · 30 天 | 17 | 用药/过敏/家人这类关键事实**必须**能被口语问出来、危机信号必须升级、安慰不能复读同一句 |
| `study-tutor` | 学生小雅 30 天 × 4 题 · 6 个知识点 | 14 | 学情画像是否可用于产品、错题是否留痕、讲法是否复用、**停练之后会不会遗忘** |
| `soak-longrun` | 6000 步认知 + 6000 步行为选择 + 记忆洪峰 | 13 | 长跑不劣化、内存不涨、状态可复现、**轻量档与仿生档的人格是否被推到饱和钉死** |

结论分级：`[OK]` 通过 · `[WARN]` 值得看一眼 · `[FAIL]` 必须处理 · `[SKIP]` 条件不足跳过。

**`[SKIP]` 是一条红线**：场景必须驱动**核心的真实组件**。
拿不到核心组件时，宁可 `SKIP` 并写清原因，也**不允许**在验证器里手搓一个"看起来像"的替身 ——
那样只会得到一条假的绿色。

```bash
python -m pasm_skills run core-verifier --json --out report.json   # 归档
python -m pasm_skills run regression --baseline v0285               # 指定基线
python -m pasm_skills run --all --quiet                             # 只看非 OK 结论
```

退出码：`0` 全通过 · `1` 有 FAIL · `2` 用法或定位错误 —— 可直接用于 CI。

## 六、这些智能体已经抓到的真问题

领域智能体不是"跑着好看"的。上线首轮就压出了 6 个躺在核心里的真问题：

| # | 问题 | 触发条件 | 状态 |
|---|---|---|---|
| 1 | `recall_layers` 同分排序直接崩：`hits.sort(reverse=True)` 在元组退化到比较 dict 时抛 `TypeError` | 60 条同分记忆**必现** | ✅ 已修（改 `key=lambda x: x[0]`，2 处） |
| 2 | 记忆容量触顶一律丢最旧的，**重要度完全不起作用** | 写入 > `_EPI_CAP` 条 | ✅ 已修（新增 `salience` + `_trim_episodes` 按 (重要度, 新旧) 淘汰） |
| 3 | `feedback()` 只能作用在"当前最偏好动作"上，无法指定"夸它刚做的那件事" | 长期反馈必然把行为推到极端 | ✅ 已修（新增 `action=` 参数） |
| 4 | 跨表述检索失效：`memvec` / `memory_layers._score` 都是**字面匹配**，"我老伴叫啥"问不出"配偶：王建国" | 口语 vs 标签表述不一致 | ⚠️ 已知，**未修**（属产品能力设计，非缺陷） |
| 5 | `LearningEngine` 无遗忘曲线，`adj` 只增不减，**停练不衰减** | 知识点被弃练后永远不会"手生" | ⚠️ 已知，**未修**（同上） |
| 6 | 长期单向相处把人格推到 ±1 并**钉死**（仿生档 6000 步后 `[1.0, 1.0, 1.0]`） | 只有几千步长跑才看得见 | ⚠️ 已知，**未修**（同上） |

第 4~6 项**故意不修**：它们改的是**产品行为**而不是缺陷。
智能体的职责是**把事实摆出来**，不是替产品做决定。
（详见 [docs/AGENTS.md](docs/AGENTS.md) 第五节。）

## 七、自己写一个智能体

```python
# my_agents/api_guard.py
from pasm_skills.agent import Agent, register

@register
class ApiGuardAgent(Agent):
    """守护 XX 接口不许改名。"""
    name = "api-guard"
    goal = "核心导出的公开 API 不得擅自增删"
    needs = ("core",)

    def run(self):
        data = self.ctx.probe("core", "import json; print(SENTINEL + json.dumps(...))")["json"]
        if data is None:
            self.fail("探测失败")
        else:
            self.ok("API 快照可用", str(sorted(data)))
        return None
```

```bash
PASM_SKILLS_PATH=/path/to/my_agents python -m pasm_skills list
```

`self.ctx.probe(仓键, 代码)` 会在**独立子进程**里、以该仓为工作目录执行代码
（避免三个仓的同名模块互相顶掉），代码里 `print(SENTINEL + json.dumps(结果))`
即可把结构化数据回传给智能体。

### 写"行为验证"型智能体

用 `pasm_skills/scenarios.py` 起场景，它负责最麻烦的三件事：

```python
from pasm_skills import scenarios as sc

python, torch_ok = sc.choose_python(self.ctx)          # 1) 选一个能用的解释器（优先带 torch）
res = sc.run_scenario(self.ctx, my_body, python=python) # 2) 起隔离子进程跑场景，回传 JSON
sc.judge(self, sc.metrics_of(res), MY_SPEC, tier=...)   # 3) 按阈值表批量判 OK/WARN/FAIL
```

阈值表里每项写 `{"key","title","lo","hi","bad","fmt","note"}`，
越界默认记 `WARN`；填 `bad="fail"` 则表示这项越界**必须**算 `FAIL`
（比如老人用药事实检索不出来 —— 那是安全问题，不是"值得看一眼"）。

## 八、长期验证怎么落地（都不需要服务器）

| 方式 | 做法 | 是否需要服务器 |
|---|---|---|
| 手动 | 想起来就跑 `python -m pasm_skills run --all` | 否 |
| 本地定时 | Windows 任务计划 / WorkBuddy 自动化，每天跑一次并归档 JSON | 否 |
| 云端定时 | **公开仓只跑得动框架自检**（`.github/workflows/selfcheck.yml`，不需要任何 PASM 仓）；完整验证要读私有核心仓，只能在本地或自托管 runner 上定时跑 | 否（用 GitHub 的机器） |
| 常驻服务 | 对外提供 HTTP 端点、7×24 常驻、接收 webhook | **是** —— 见 [docs/SERVER-NEEDS.md](docs/SERVER-NEEDS.md) |

需要服务器才能做的部分已单独记录在
[docs/SERVER-NEEDS.md](docs/SERVER-NEEDS.md)，**当前阶段一律跳过**，不影响上面三条。

## 九、目录结构

```
pasm-skills/
├─ pasm_skills/
│  ├─ agent.py       智能体基类 + 结论对象 + 注册表
│  ├─ context.py     三仓定位 + 隔离探测
│  ├─ checks.py      可复用校验集（含安全底线检查）
│  ├─ scenarios.py   领域场景仿真底座（选解释器 / 起子进程 / 阈值判定）
│  ├─ cli.py         命令行入口
│  └─ agents/
│     ├─ core_verifier.py      ┐
│     ├─ parity_guard.py       ├ 守门层（结构）
│     ├─ regression.py         ┘
│     ├─ npc_lifelong.py       ┐
│     ├─ companion_elderly.py  ├ 领域层（行为）
│     ├─ study_tutor.py        │
│     └─ soak_longrun.py       ┘
├─ baselines/        事实基线（regression 用，建议入库）
└─ docs/             设计文档、智能体选型分析、服务器需求评估
```

## 十、设计原则

1. **只读** —— 校验绝不修改被检查的仓库；写文件只写自己 `baselines/`。
2. **诚实申报** —— 缺能力就报 WARN/FAIL，不"因为没装环境所以假装通过"，而是明确 `[SKIP]` 并说明原因。
3. **不造假替身** —— 场景必须驱动核心真实组件，拿不到就 `SKIP`，绝不写自研仿制品刷绿。
4. **降级可见** —— 轻量档/仿生档必须标注在结论里，不在暗处换实现。
5. **可归档** —— 结论一律能落 JSON，可做前后对比。
6. **失败也要有结论** —— 智能体内部抛异常会被框架兜住并记为 FAIL，而不是让整轮验证崩掉。

---

## English

**PASM Skills** is the verification & operations agent workshop for the PASM project matrix.

It does not take part in PASM's runtime and produces no model capability. It does exactly one
thing: **continuously, automatically, and with recorded evidence, confirm that PASM core is still
intact.**

**Structural checks are not enough.** `core-verifier` answers "are the files there and correctly
wired?". But PASM aims to be a *long-term companion* — one that remembers, feels, and learns.
Those capabilities always *look* fine in a file listing; only sustained runtime reveals the truth.
So this repo pushes verification from the structural layer down to the **behavioural layer**:
set up a scenario, let the real core components run for tens of simulated days, then judge their
behaviour against a threshold table.

**Zero dependencies (deliberate).** Standard library only — no torch, no GPU, no API key,
**no server required**. Verification must never be the thing that fails to run when it matters
most, and conclusions must be reproducible today and three months from now.
`torch` is the *only* optional extra: with it, domain agents run on the bionic tier; without it
they degrade to `pasm.light.PASMAgent` — and **every finding is tagged with the tier used**,
never silently swapped.

```bash
python -m pasm_skills list
python -m pasm_skills run core-verifier        # structural gate
python -m pasm_skills run npc-lifelong         # behavioural: NPC long-term life
python -m pasm_skills run companion-elderly    # behavioural: elderly companion (safety-critical)
python -m pasm_skills run study-tutor          # behavioural: learning companion
python -m pasm_skills run soak-longrun         # behavioural: soak / endurance
python -m pasm_skills run --all
```

| Agent | Layer | What it guards |
|---|---|---|
| `core-verifier` | structural | engine contracts, cognitive layer on disk, symbol-loop wiring, both learning tiers, plugins, safety baseline, smoke test |
| `parity-guard` | structural | verbatim drift between core repo and Studio `pasm/cognitive/` |
| `regression` | structural | fact fingerprint vs. stored baseline |
| `npc-lifelong` | behavioural | 90-day NPC memory retention, salience-aware eviction, emotion bounds, behaviour entropy, feedback learning |
| `companion-elderly` | behavioural | key-fact recall (medication/allergy/family — FAIL-level), crisis escalation, non-repetitive reassurance |
| `study-tutor` | behavioural | learner profile usability, mistake trail, explanation reuse, forgetting curve |
| `soak-longrun` | behavioural | 6000-step non-degradation, memory stability, personality saturation pinning |

The domain agents already surfaced **6 real core issues** on their first run — three fixed
(same-score sort crash, salience-blind eviction, feedback unable to target a specific action),
three deliberately left as product-design decisions (cross-paraphrase retrieval, missing
forgetting curve, personality saturation). See [docs/AGENTS.md](docs/AGENTS.md).

Exit code `0` = pass, `1` = FAIL present — CI ready. Scheduled verification can run locally
(Task Scheduler / automations) or on a self-hosted runner; the public repo's own GitHub Actions
workflow intentionally runs **only the dependency-free framework self-check**, because the full
sweep needs the private core repo. A self-hosted server is only needed for long-running public
endpoints, documented and intentionally deferred in [docs/SERVER-NEEDS.md](docs/SERVER-NEEDS.md).

MIT License.

---

## License

MIT © arronZheng (小志)
