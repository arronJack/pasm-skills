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

## 二、零依赖设计（刻意的）

只用 Python 标准库。不需要 torch、不需要 GPU、不需要 API key、**不需要服务器**。

理由不是"图省事"：

- **断网/无显卡/无 token 也要能跑** —— 验证器一旦有依赖，就会在关键时刻跑不起来；
- **结论只由代码事实决定** —— 不引入 LLM 的不确定性，避免"AI 说没问题"式的假安全感；
- **任何机器、任何时间、可重复** —— 今天和三个月后跑出的结论必须能直接对比。

需要"会思考"的智能体时，在 `run()` 里自己调 LLM 即可，框架不拦、也不强制。

## 三、快速开始

```bash
cd pasm-skills

# 1) 看环境：三仓定位 + 智能体清单
python -m pasm_skills list

# 2) 给核心做一次全量体检
python -m pasm_skills run core-verifier

# 3) 存一次"事实基线"（此后任何退化都会被自动抓到）
python -m pasm_skills run regression --update

# 4) 跑全部
python -m pasm_skills run --all
```

Python 3.10+。仓库路径默认按约定查找（`E:/AI/PASM`、`E:/AI/pasm_qclaw`、`E:/AI/PASM_LITE`），
也可用环境变量显式指定：

```bash
export PASM_CORE=/path/to/PASM
export PASM_STUDIO=/path/to/pasm_qclaw
export PASM_LITE=/path/to/PASM_LITE
export PASM_PYTHON=/path/to/python      # 用哪个解释器做探测（默认当前解释器）
```

## 四、内置智能体

| 名字 | 作用 | 需要仓库 |
|---|---|---|
| `core-verifier` | 全量体检：引擎契约 / 认知层是否真落盘 / 符号闭环接线 / 学习层两档 / 环境插件 / 端到端冒烟 | core |
| `parity-guard` | 核心仓 ↔ Studio 仓 `pasm/cognitive/` 逐字一致守门 | core, studio |
| `regression` | 采集事实指纹，与基线比对，抓静默退化 | core |

结论分级：`[OK]` 通过 · `[WARN]` 值得看一眼 · `[FAIL]` 必须处理 · `[SKIP]` 条件不足跳过。

```bash
python -m pasm_skills run core-verifier --json --out report.json   # 归档
python -m pasm_skills run regression --baseline v0285              # 指定基线
```

退出码：`0` 全通过 · `1` 有 FAIL · `2` 用法或定位错误 —— 可直接用于 CI。

## 五、自己写一个智能体

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

## 六、长期验证怎么落地（都不需要服务器）

| 方式 | 做法 | 是否需要服务器 |
|---|---|---|
| 手动 | 想起来就跑 `python -m pasm_skills run --all` | 否 |
| 本地定时 | Windows 任务计划 / WorkBuddy 自动化，每天跑一次并归档 JSON | 否 |
| 云端定时 | 推送到本公开仓，用 **GitHub Actions** 定时跑（公开仓免费） | 否（用 GitHub 的机器） |
| 常驻服务 | 对外提供 HTTP 端点、7×24 常驻、接收 webhook | **是** —— 见 [docs/SERVER-NEEDS.md](docs/SERVER-NEEDS.md) |

需要服务器才能做的部分已单独记录在
[docs/SERVER-NEEDS.md](docs/SERVER-NEEDS.md)，**当前阶段一律跳过**，不影响上面三条。

## 七、目录结构

```
pasm-skills/
├─ pasm_skills/
│  ├─ agent.py       智能体基类 + 结论对象 + 注册表
│  ├─ context.py     三仓定位 + 隔离探测
│  ├─ checks.py      可复用校验集（智能体从中拼装）
│  ├─ cli.py         命令行入口
│  └─ agents/        内置智能体
├─ baselines/        事实基线（regression 用，建议入库）
└─ docs/             设计文档与服务器需求评估
```

## 八、设计原则

1. **只读** —— 校验绝不修改被检查的仓库；写文件只写自己 `baselines/`。
2. **诚实申报** —— 缺能力就报 WARN/FAIL，不"因为没装环境所以假装通过"，而是明确 `[SKIP]` 并说明原因。
3. **可归档** —— 结论一律能落 JSON，可做前后对比。
4. **失败也要有结论** —— 智能体内部抛异常会被框架兜住并记为 FAIL，而不是让整轮验证崩掉。

---

## English

**PASM Skills** is the verification & operations agent workshop for the PASM project matrix.

It does not take part in PASM's runtime and produces no model capability. It does exactly one
thing: **continuously, automatically, and with recorded evidence, confirm that PASM core is still
intact.**

**Zero dependencies (deliberate).** Standard library only — no torch, no GPU, no API key,
**no server required**. Verification must never be the thing that fails to run when it matters
most, and conclusions must be reproducible today and three months from now.

```bash
python -m pasm_skills list
python -m pasm_skills run core-verifier
python -m pasm_skills run --all
```

Built-in agents: `core-verifier` (full core health check), `parity-guard` (core vs. Studio
cognitive-layer drift), `regression` (fact fingerprint vs. baseline).

Exit code `0` = pass, `1` = FAIL present — CI ready. Scheduled verification can run locally
(Task Scheduler / automations) or on **GitHub Actions for free**; a self-hosted server is only
needed for long-running public endpoints, which are documented and intentionally deferred in
[docs/SERVER-NEEDS.md](docs/SERVER-NEEDS.md).

MIT License.

---

## License

MIT © arronZheng (小志)
