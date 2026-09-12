# PASM Skills · 智能体工坊

> **本仓是 PASM 的"产品智能体"与"质量守门员"的两层工坊。**
>
> **产品层** 提供三类基于 PASM 引擎、可立即装载使用的智能体：
> 游戏 NPC / 老人陪伴 / 学习陪伴。零 LLM 依赖、断网可用、状态可持久化。
>
> **验证层** 提供四类对 PASM 核心做长期体检的智能体：核心契约 /
> 仓对齐 / 回归基线 / 长效耐久 —— **这些"质检智能体"反过来给产品层兜底**。

---

## 一、产品智能体（pasm_agents）

**它们是真智能体，不是测试**。`pip install` 完之后：

```python
from pasm_agents import NpcAgent, ElderlyCompanion, LearningTutor

# 河边摆摊的草药老头 —— 有记忆、有性格、能对话、能被反馈调整
npc = NpcAgent(agent_id="herbalist", persona={
    "name": "陈伯", "role": "河边摆摊的草药老头",
    "temper": 0.55, "energy": 0.40, "play": 0.30,
    "tone": "慢悠悠、爱讲道理",
})
npc.observe("玩家第一次来买跌打药", salience=5, tags=["玩家", "救命"])
print(npc.act())                 # -> ' wave' / 'talk' / 'peek' …
print(npc.chat("你叫什么名字"))   # -> ' 陈伯道：…'
npc.feedback("praise", action="talk")  # 显式指明被夸的是哪个动作
npc.save()                       # ~/.pasm-agents/herbalist/agent_state.json
```

```python
# 老人陪伴 —— 关键事实牢牢记住 + 危机自动识别
comp = ElderlyCompanion(agent_id="chenxiulan", persona={
    "name": "陈秀兰", "age": 78,
    "key_facts": [
        {"label": "用药", "content": "每天早 8 点吃降压药络活喜 5mg"},
        {"label": "过敏", "content": "青霉素过敏"},
        {"label": "家人", "content": "女儿在深圳，每周日来电话"},
        {"label": "本人", "content": "78 岁，独居"},
    ],
    "emergency_contact": {"name": "女儿小敏", "phone": "13900000000"},
    "medication_schedule": [{"name": "络活喜", "dose": "5mg", "hour": 8}],
})
print(comp.chat("我吃什么药"))           # 关键事实直查
print(comp.detect_crisis("卫生间滑倒"))  # ['摔倒/外伤']
print(comp.escalate("卫生间滑倒"))       # 写入紧急记忆 + 返回升级信息
```

```python
# 学习陪伴 —— 薄弱点定位 + 自适应选题
t = LearningTutor(agent_id="xiaoya", persona={
    "name": "小雅", "grade": "五年级",
    "topics": ["分数加减", "面积计算", "行程问题", "鸡兔同笼"],
})
t.report("分数加减", 0.4)   # 报告作答分数
print(t.pick_next())        # -> '分数加减'（最弱优先）
print(t.chat("分数加减好难"))  # -> 鼓励 + 具体下一步
```

### 30 秒上手

```bash
git clone https://gitee.com/arronzheng/pasm-skills
cd pasm-skills
pip install -e .

# 三类智能体的预置剧本 —— 立刻看到效果，无需任何环境
pasm-agents demo npc
pasm-agents demo companion
pasm-agents demo tutor

# 进入交互模式（输入 quit 退出并 save）
pasm-agents run npc --id=my_herbalist
pasm-agents run companion --id=my_companion --persona-file=personas/chenxiulan.json

# 列出本机 agent / 查看快照
pasm-agents list
pasm-agents inspect my_herbalist
```

### 落盘位置

`~/.pasm-agents/<agent_id>/`

```
agent_state.json       # 状态（persona / 交互数 / 反馈历史 / mood / 备注）
episodes.json          # light 档位下的记忆（核心档位走 pasm.cognitive.memory_layers）
action_weights.json    # light 档位下的动作权重
```

### 档位透明 —— 不隐藏降级

| 档位 | 含义 | 何时启用 |
|---|---|---|
| `bionic` | 仿生：完整 PASM 核心 + emotion 模块（需 torch） | `pip install pasm-skills[torch]` 并装有 torch 时 |
| `core`    | 完整：PASM 核心（memory + learning，不需 torch） | `PASM_PYTHON` 指向带核心的 Python 时 |
| `light`   | 轻量：纯内置（重要度淘汰 + 字面检索 + softmax 权重） | 任何机器都可跑 |

每个 agent 的 `summary()` / 落盘 JSON 都会带 `tier` 字段，调用方一眼就能判断当前档位。

---

## 二、质量守门员（pasm_skills.agents）—— *反向* 守住产品层

产品层有了，但"它跑久了还是好的吗？"这类问题**产品层自己答不上来**。
于是本仓还有第二层：**对 PASM 核心做长期行为体检**。

这些不是"模拟跑 90 天然后 [OK] / [FAIL]" 的检查项，
是**智能体** —— 每个都驱动核心真实组件，隔离子进程跑几天，跑完后压出真实问题。

| 验证智能体 | 检查什么 | 当前结果 |
|---|---|---|
| `core-verifier`     | 32 项核心契约 / 安全底线 / 环境插件 | 33 ok / 1 warn / 0 fail |
| `parity-guard`      | 两仓核心内容逐字一致 | OK |
| `regression`        | 关键指纹与基线比对（基线解释器档位锁定） | OK |
| `npc-lifelong`      | 90 天 / 270 段经历 —— 核心能否正确记忆 NPC | 19 ok / 0 warn / 0 fail |
| `companion-elderly` | 30 天老人陪伴 —— 关键事实 100% 检索、危机命中 | 13 ok / 4 warn |
| `study-tutor`       | 30 天学习陪伴 —— 学情结构 + 巩固 | 14 ok / 1 warn |
| `soak-longrun`      | 6000 步认知 + 行为 + 记忆洪峰 —— 长效耐久 | 13 ok / 2 warn |

> 这层**反向**帮产品层兜底：
> 验证智能体压出的「同分排序崩溃 / 容量淘汰无重要度 / 反馈无法指定动作」等真问题，
> 已经被修进 `pasm_agents/base.py` 的 `_CoreAdapter` 里 —— **产品层在用就是修过的版本**。

---

## 三、安装

```bash
# 纯产品层（无 torch 也能跑，tier=light）
pip install pasm-skills

# 想要完整档位（tier=core / bionic）
pip install pasm-skills[torch]

# 开发模式
git clone https://gitee.com/arronzheng/pasm-skills
cd pasm-skills
pip install -e .
```

无 torch 时，`pasm-agents demo` / `pasm-skills run` 都正常 —— `tier` 字段会如实告诉你当前在哪一档。

## 四、目录

```
pasm-skills/
├── pasm_agents/             ★ 产品智能体（打开仓第一眼应该看到的）
│   ├── base.py              BaseAgent：观测/记忆/情绪/动作/持久化
│   ├── npc.py               NpcAgent —— 游戏 NPC（性格 + 记忆 + 情绪 + 成长动作）
│   ├── companion.py         ElderlyCompanion —— 老人陪伴（关键事实 + 用药 + 危机）
│   ├── tutor.py             LearningTutor —— 学习陪伴（薄弱点 + 巩固）
│   └── cli.py               pasm-agents 命令行
│
├── pasm_skills/             ★ 质量守门员（质检智能体）
│   ├── agents/              7 个验证智能体（core/parity/regression + 4 领域）
│   ├── scenarios.py         场景仿真底座
│   ├── checks.py            32 项核心契约 + 安全底线
│   ├── agent.py             Agent 基类
│   ├── context.py           仓上下文
│   └── cli.py               pasm-skills 命令行
│
├── examples/                可直接运行的 30 秒示例
│
├── docs/                    选型分析 / 架构说明 / 服务器需求评估
│   ├── AGENTS.md            智能体设计手册（验证 + 产品两章）
│   ├── ARCHITECTURE.md
│   └── SERVER-NEEDS.md
│
├── skill/                   技能包正文（两种归档形态共用一份）
├── tools/                   打包脚本
├── baselines/               事实基线（regression 用，建议入库）
└── reports/                 本地跑出来的报告（gitignore）
```

## 五、发布

技能包由一个正文生成**两种归档形态** —— 按**结构**命名，不按平台名（平台会变，结构不会）：

| 形态 | 归档结构 | frontmatter | 产物 |
|---|---|---|---|
| `zip-root` | ZIP **根目录直接是 `SKILL.md`** | 完整（display_name / description_zh / description_en / requires） | `dist/zip-root/<name>/SKILL.md` |
| `slug-dir` | 以 slug 命名的**目录**，内含 `SKILL.md` | 最小（name / description / version / license / metadata） | `dist/slug-dir/<name>/SKILL.md` |

```bash
python tools/build_skill.py --zip --clean
```

> ⚠️ `zip-root` 形态**必须**把 `SKILL.md` 放在 ZIP 根目录。包成 `skills/<name>/SKILL.md`
> 会被平台拒收（报「压缩包缺少 SKILL.md 文件」）—— 平台不递归找。脚本已内置校验。

当前状态：

| 技能 | 状态 |
|---|---|
| `pasm-longterm-verify` | v0.2.1 —— 已提交技能平台审核 / 已发布到 ClawHub |
| `pasm-agents`          | v0.3.0 —— 待发布（产品层入口） |
| 源码                   | GitHub `arronJack/pasm-skills` + Gitee `arronzheng/pasm-skills` 双端同步 |

各平台的登录方式、审核流程与更新步骤记在**仓库外**的本机发布指南里，
不随公开仓分发（避免把个人操作细节和平台专名混进项目文档）。

## 六、本机配置（可选）

`pasm-skills.local.json`（**`.gitignore` 已忽略，绝不入库**）用来指定本机上带 torch 的解释器：

```json
{ "python": ["/path/to/python-with-torch"] }
```

- 找得到 → 领域场景跑 `bionic` 档（真实情绪模块 + 人格）
- 找不到 → 自动降级 `core` / `light`，并在**每条结论**里标注档位，绝不假装覆盖了

优先级：`PASM_TORCH_PYTHON` → `PASM_PYTHON` → 本配置文件 → 当前解释器 → 仓库内 venv → `PATH`。

**公开仓里不留任何个人机器路径** —— 这也是回归基线只记 Python 版本号、不记路径的原因。

## 七、许可证

MIT。
