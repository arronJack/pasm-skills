# 架构说明（ARCHITECTURE）

## 一、分层

```
CLI (cli.py)
  │  list / repos / run / selftest
  ▼
智能体 (agents/*.py)          ← 只负责"编排检查项 + 汇报结论"
  │  Agent.run() → self.ok/warn/fail/skip(...)
  ▼
校验集 (checks.py)            ← 只负责"怎么查"，可被任意智能体复用
  │  check_contract / check_cognitive_layers / check_symbolic_loop / ...
  ▼
上下文 (context.py)           ← 只负责"查哪里"与"怎么隔离地查"
  │  RepoContext.probe(仓键, 代码)
  ▼
被检查的仓库  core=PASM · studio=pasm_qclaw · lite=PASM_LITE
```

设计意图：**检查项与检查主体解耦**。
`check_contract` 不关心是谁在跑它；`parity-guard` 和 `core-verifier` 可以共用同一个检查；
新智能体通常只是"挑几个现有检查 + 加一条自己的"。

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

## 三、结论模型

```python
Finding(level, title, detail)      # 一条结论
AgentResult(agent, ok, findings, elapsed, error, extra)   # 一次运行
```

- 四个等级：`OK` / `WARN` / `FAIL` / `SKIP`，`worst()` 取最差；
- `SKIP` 是一等公民：**条件不足要明说**，绝不用"通过"掩盖"没查"；
- 智能体内部抛异常由框架兜住 → 记为 `FAIL` 并附异常文本，
  保证"一个智能体崩了不会毁掉整轮验证"；
- `to_dict()` 保证可序列化 → CLI 直接 `--json --out` 归档。

## 四、内置检查项一览（checks.py）

| 检查 | 内容 | 典型失败原因 |
|---|---|---|
| `check_contract` | `pasm.engine_api` 可导入；内置引擎能创建且 `conforms(strict)`；快照七区块齐全 | 契约漂移、打包漏模块 |
| `check_cognitive_layers` | 13 个认知层文件在核心包全在、可导入、自检通过 | "只在 Studio 实现、核心没落盘" |
| `check_symbolic_loop` | `solve/verify/prompt_block/writeback/set_memory_sink` + 记忆路由 `route/classify` | 闭环断点 |
| `check_learning_contract` | 核心档与 Lite 档学习层都在、自检通过、声明同一接口 | 两档实现漂移 |
| `check_env_plugins` | `env_registry()` 可用（环境可插拔） | 环境写死网格世界 |
| `check_smoke` | Lite 引擎 `create → act → learn → snapshot` 端到端 | 运行时断裂 |
| `check_parity` | 核心仓 ↔ Studio 仓 `pasm/cognitive/*.py` 逐字一致（忽略 CRLF） | 两仓分叉 |

## 五、新增智能体的推荐姿势

1. 先看 `checks.py` 里有没有能直接用的检查项；
2. 没有的话，写一段"在目标仓里跑起来、打印 JSON"的探测代码，
   用 `self.ctx.probe(...)` 执行；
3. 把结果翻译成 `ok/warn/fail/skip`，**不要自己 print 判断**；
4. `needs` 声明依赖的仓库，框架会自动做缺失跳过。

## 六、不做的事

- **不自动修复** —— 验证器的可信度来自"只报告、不动手"。修复走 PASM 正常的开发流程。
- **不依赖 LLM** —— 保持确定性与可复现性；需要时由具体智能体自行引入。
- **不写被检查仓库** —— 只写自己的 `baselines/`。
- **不做定时** —— 调度交给操作系统或 CI，`pasm-skills` 只提供可被调度的 CLI。
