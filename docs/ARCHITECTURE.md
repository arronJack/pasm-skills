# 架构说明（ARCHITECTURE）

## 一、分层

```
CLI (cli.py)
  │  list / repos / run / selftest
  ▼
智能体 (agents/*.py)          ← 只负责"编排检查项 + 汇报结论"
  │  Agent.run() → self.ok/warn/fail/skip(...)
  ├──────────────────────────────────────────────┐
  │ 守门层（结构）                                 │ 领域层（行为）
  ▼                                              ▼
校验集 (checks.py)                       场景底座 (scenarios.py)
  │  check_contract / check_cognitive_layers │  choose_python / run_scenario / judge
  │  check_symbolic_loop / check_safety...   │  PRELUDE + 阈值表
  └────────────────┬─────────────────────────┘
                   ▼
        上下文 (context.py)           ← 只负责"查哪里"与"怎么隔离地查"
          │  RepoContext.probe(仓键, 代码)
          ▼
被检查的仓库  core=PASM · studio=pasm_qclaw · lite=PASM_LITE
```

设计意图：**检查项与检查主体解耦**。
`check_contract` 不关心是谁在跑它；`parity-guard` 和 `core-verifier` 可以共用同一个检查；
新智能体通常只是"挑几个现有检查 + 加一条自己的"。

**两条验证路径的关系**：

| | 守门层（checks.py） | 领域层（scenarios.py） |
|---|---|---|
| 问的问题 | 东西在不在、接线对不对 | 跑起来表现对不对 |
| 检查方式 | 静态探测（导入、读文件、比快照） | **起场景、让真实组件真跑** |
| 耗时 | 秒级 | 秒~分钟级（`soak-longrun` 约 1~2 分钟） |
| 失效类型 | 模块缺失、契约漂移、两仓分叉 | 记忆丢失、情绪漂移、行为僵化、人格饱和 |

两者不互相替代：`core-verifier` 全绿**不能**保证 NPC 记得住玩家。

## 二、关键决策：为什么探测要开子进程

三个仓存在**同名模块**：

```
PASM/pasm/cognitive/symbolic.py          ← 核心（单一真相源）
pasm_qclaw/desktop/symbolic.py           ← Studio 的兼容薄壳
PASM_LITE/learning.py                    ← 教学版学习层
PASM/pasm/cognitive/learning.py          ← 核心学习层（同名不同物）
```

若在同一解释器里逐个 `import`，`sys.modules` 会互相顶掉，**先导入的那个会污染后一个**，
结论就完全不可信了（这正是"看起来查了，其实查错对象"的典型陷阱）。

所以 `RepoContext.probe()` 每次都：

1. 起一个**全新解释器**；
2. `sys.path[0]` 指向目标仓；
3. `cwd` 设为目标仓；
4. 清掉继承来的 `PYTHONPATH`；
5. 代码里 `print(SENTINEL + json.dumps(obj))` 回传结构化结果，其余 stdout/stderr 原样保留。

代价是每次多几十毫秒，换来的是**结论可复现**。对长期验证来说这笔账非常划算。

## 三、场景底座（scenarios.py）

领域智能体要跑"几十天""几千步"，必须解决三个问题，`scenarios.py` 正好各管一件：

### 3.1 用哪个解释器

`choose_python(ctx, prefer_torch=True)` 按候选顺序找一个能用的解释器：

```
PASM_TORCH_PYTHON → PASM_PYTHON → 本机配置(~/.pasm-skills/local.json)
  → sys.executable → 仓库内 venv(.venv / venv) → py → python3 → python
```

返回 `(python, torch_ok)`，结果带缓存。**`torch_ok` 决定跑哪一档**：
装了 torch 走仿生档（真实脉冲 + 人格模块），没装降级到 `pasm.light.PASMAgent`。
这个档位会一路传到 `judge(tier=...)`，**写进每一条结论里**。

> 本机那个"带 torch 的解释器"往往在仓库外，所以它走**仓库外的本机配置文件**
> （`~/.pasm-skills/local.json`，可用 `PASM_LOCAL_CONF` 改路径）而不是硬编码 ——
> 公开仓里不留任何个人机器路径。

### 3.2 场景代码怎么送进去

`PRELUDE` 是一段裸函数文本，会**拼在场景代码前面**一起注入子进程。
它提供的是场景最常用、又最容易写错的小工具：

| 函数 | 用途 |
|---|---|
| `emit(obj)` | 回传 JSON 给智能体 |
| `entropy` / `norm_entropy` | 行为分布是否僵化（熵塌缩） |
| `tv_distance` | 两个分布的差异（反馈学习到底有没有生效） |
| `topk_by` / `hits_in` / `ghost_max` | 检索质量：能不能检到、有没有检出"鬼" |
| `bounded` / `max_jump` / `span` | 数值序列是否越界、有没有突跳 |
| `mean` / `rate` / `slope` | 均值、占比、趋势（遗忘曲线） |
| `temp_layers` / `cleanup(d)` | 建临时目录、用完清掉 |
| `TORCH_OK` | 当前子进程有没有 torch |

**关键点**：`PRELUDE` 里**只有纯函数**，不含任何"替身实现"。
真实的核心组件一律**从被检查的仓库里 `import`**；
拿不到就 `SKIP` 并说明原因 —— 这是本仓的**红线**，见第六节。

### 3.3 结果怎么判

```python
judge(agent, metrics, spec, tier="")
```

`spec` 每项形如：

```python
{"key": "route_acc", "title": "记忆路由准确率",
 "lo": 0.75,              # 下界
 "hi": None,              # 上界
 "bad": "warn",           # 越界算 warn 还是 fail
 "fmt": "%.3f",           # 打印格式
 "note": "低于 0.75 说明路由开始乱指"}
```

- 默认越界记 `WARN` —— "值得看一眼"；
- `bad="fail"` 则必须算 `FAIL` —— 用于**安全关键项**
  （例：老人用药/过敏事实检索不出来，那是安全问题，不是"看一眼"）；
- 返回越界项数量，方便智能体判断整体成色。

## 四、结论模型

```python
Finding(level, title, detail)      # 一条结论
AgentResult(agent, ok, findings, elapsed, error, extra)   # 一次运行
```

- 四个等级：`OK` / `WARN` / `FAIL` / `SKIP`，`worst()` 取最差；
- `SKIP` 是一等公民：**条件不足要明说**，绝不用"通过"掩盖"没查"；
- 智能体内部抛异常由框架兜住 → 记为 `FAIL` 并附异常文本，
  保证"一个智能体崩了不会毁掉整轮验证"；
- `extra` 存场景产出的原始数据（指标字典）。
  它会被并进 `AgentResult.extra`、写进归档 JSON
  —— **"长期验证"要的就是这个可比性**：前后两次运行能逐项对比。
- `to_dict()` 保证可序列化 → CLI 直接 `--json --out` 归档。

## 五、内置检查项一览（checks.py）

| 检查 | 内容 | 典型失败原因 |
|---|---|---|
| `check_contract` | `pasm.engine_api` 可导入；内置引擎能创建且 `conforms(strict)`；快照七区块齐全 | 契约漂移、打包漏模块 |
| `check_cognitive_layers` | 13 个认知层文件在核心包全在、可导入、自检通过 | "只在 Studio 实现、核心没落盘" |
| `check_symbolic_loop` | `solve/verify/prompt_block/writeback/set_memory_sink` + 记忆路由 `route/classify` | 闭环断点 |
| `check_learning_contract` | 核心档与 Lite 档学习层都在、自检通过、声明同一接口 | 两档实现漂移 |
| `check_env_plugins` | `env_registry()` 可用（环境可插拔） | 环境写死网格世界 |
| `check_safety_readiness` | `pasm/` 下是否有安全底线层（风险/危机/隐私/未成年保护） | 只有业务能力、没有安全兜底 |
| `check_smoke` | Lite 引擎 `create → act → learn → snapshot` 端到端 | 运行时断裂 |
| `check_parity` | 核心仓 ↔ Studio 仓 `pasm/cognitive/*.py` 逐字一致（忽略 CRLF） | 两仓分叉 |

`check_safety_readiness` 的匹配词表刻意收得很紧（`自伤`/`危机干预`/`未成年人保护`/`隐私保护`…）。
早期版本图省事塞了 `120`、`红线` 这类短词，结果撞上 `[:120]` 切片下标和"质量红线"这种注释，
**报出 9 处假命中**。教训：**安全类检查宁可漏报语义线索，也不能假绿**。

## 六、不做的事（红线）

- **不自动修复** —— 验证器的可信度来自"只报告、不动手"。修复走 PASM 正常的开发流程。
- **不造假替身** —— 场景必须驱动**核心真实组件**。拿不到就 `SKIP` 并写清原因，
  绝不在验证器里手搓一个"看起来像"的仿制品。**假绿比没查更危险。**
- **不隐藏降级** —— 轻量档/仿生档必须标在结论里。
- **不依赖 LLM** —— 保持确定性与可复现性；需要时由具体智能体自行引入。
- **不写被检查仓库** —— 只写自己的 `baselines/`。
- **不做定时** —— 调度交给操作系统或 CI，`pasm-skills` 只提供可被调度的 CLI。

## 七、新增智能体的推荐姿势

1. 先看 `checks.py` 里有没有能直接用的检查项；
2. 没有的话，写一段"在目标仓里跑起来、打印 JSON"的探测代码，
   用 `self.ctx.probe(...)` 执行；
3. 把结果翻译成 `ok/warn/fail/skip`，**不要自己 print 判断**；
4. `needs` 声明依赖的仓库，框架会自动做缺失跳过；
5. 要写"跑几十天"的行为验证，用 `scenarios.py`（见第三节），
   **不要**在智能体里手搓时间循环和阈值判断 —— 那正是它存在的理由。
