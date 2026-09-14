# PASM Skills · 智能体基座

> **本仓是基座：只提供"写智能体"的能力，不提供成品智能体。**
> 想直接拿现成的智能体用（游戏 NPC / 老人陪伴 / 学习陪伴 / 长期验证），
> 装独立公开仓 **pasm-agents**。
>
> ```bash
> pip install pasm-skills      # 基座：SDK + 框架 + 打包工具（零依赖）
> pip install pasm-agents      # 成品智能体集（依赖本基座）
> ```

基座给你三样东西：

| | 是什么 | 入口 |
|---|---|---|
| **📖 使用教程** | 从"这是干什么的"到"写出并发布一个智能体"，走一遍 | **[`docs/TUTORIAL.md`](docs/TUTORIAL.md)** |
| **SDK** | `BaseAgent` —— 记忆 / 情绪 / 动作 / 反馈 / 持久化开箱可用 | `from pasm_skills.sdk import BaseAgent` |
| **认知层** | 语义检索 / 遗忘曲线 / 记忆巩固 / 焦点栈 / 心跳 / 工具注册表 | `from pasm_skills.cognition import enhance` |
| **框架** | 智能体基类与注册表、仓隔离探测、场景仿真底座、核心契约检查工具箱 | `from pasm_skills.agent import Agent, register` |
| **打包** | 把智能体打成平台可直接上传的技能包（两种归档形态） | `from pasm_skills.build import SkillSpec, run_cli` |

---

## 〇、PASM 生态索引（六仓同频）

PASM 不是一个仓，而是一套分层生态：

| 仓 | 角色 | 可见性 | 版本 |
|---|---|---|---|
| **`pasm-skills`（本仓）** | **基座**：`BaseAgent` + 认知能力层 | 公开 | **0.5.0** |
| `pasm-agents` | 成品智能体集（NPC / 陪伴 / 教学 / 验证） | 公开 | 0.4.5 |
| `pasm-mcp-server` | MCP 接入层：给任意 AI 客户端装长期记忆 | 公开 | 0.2.0 |
| `PASM-Lite` | 教学版 + 认知引擎接口 | 公开 | — |
| `PASM` | 核心引擎（七层仿生 / 世界模型） | **私有** | 0.7.2 |
| `pasm-qclaw` | 桌面应用发行通道 | 公开 | 0.29.1 |

流向：`PASM`（核心）→ `pasm-skills`（基座）→ `pasm-agents`（智能体）→
`pasm-mcp-server`（分发）→ `pasm-qclaw`（桌面产品）；`PASM-Lite` 是面向外界的教学窗口。

地址：
[Gitee](https://gitee.com/arronzheng/pasm-skills) ·
[GitHub](https://github.com/arronJack/pasm-skills)

---

## 一之二、认知能力层（0.5.0 新增）

`BaseAgent` 给的是**基础认知原语**；下面这些是长期相处才看得出差别的能力。
两行接入，**不改你已有的智能体一行代码**：

```python
from pasm_skills.cognition import enhance

cog = enhance(agent)                       # 挂上全部认知能力
cog.observe("姓名", "小明", tags=["身份"], salience=4)
cog.recall("我叫什么名字")                  # ← 字面匹配做不到，这里能命中
```

| 能力 | 解决什么 | 模块 |
|---|---|---|
| **语义检索** | 换个说法就检索不到（命中率 0.5 → 0.8+）：中文同义扩展 + 可插拔向量后端 | `cognition.semantic` |
| **遗忘曲线** | 停练 25 天和昨天一样强 → 学情失真 | `cognition.forgetting` |
| **记忆巩固** | 重复经历撑爆记忆池 → 睡眠回放蒸馏成要点 | `cognition.forgetting` |
| **焦点栈** | 长对话跑题、记不住"现在在聊什么" | `cognition.focus` |
| **心跳** | 智能体纯被动、永远不会主动开口 | `cognition.tick` |
| **工具注册表** | 动作名 ≠ 可执行工具；无法被发现、无法被授权 | `cognition.tools` |

```bash
python -m pasm_skills cognition     # 27 项自检
```

> 内置向量后端是**零依赖离线**的字符 n-gram hashing（配中文同义概念表）。
> 想要真正的语义向量，配一个 OpenAI 兼容的 embedding 接口即可自动接管：
> `PASM_EMBED_URL` / `PASM_EMBED_MODEL` / `PASM_EMBED_KEY`。

---

## 一、30 秒写一个智能体

```python
from pasm_skills.sdk import BaseAgent

class TeaHouseOwner(BaseAgent):
    def action_pool(self):                  # 能做什么
        return ["greet", "brew", "gossip", "rest"]

    def _render_reply(self, text, facts, mood):   # 怎么回
        tone = "蔫" if mood < -0.2 else "乐"
        return f"（{tone}）{self.persona.get('name')}：来了您呐"

a = TeaHouseOwner(agent_id="owner", persona={"name": "王掌柜", "temper": 0.6, "energy": 0.3})
a.observe("客人夸今年的龙井好", salience=3, tags=["茶"])   # 写记忆（重要度参与淘汰）
print(a.act())                                  # 'brew' / 'greet' / ...
print(a.chat("生意怎么样"))                      # 走 _render_reply
print(a.mood)                                   # 情绪（属性，不加括号）
a.feedback("praise", action="brew")             # 显式夸"brew"这个动作 → 它会更常出现
a.save()                                        # ~/.pasm-agents/owner/
```

跑一个完整走查（8 个环节 + 反馈塑形的实测对比）：

```bash
git clone https://gitee.com/arronzheng/pasm-skills
cd pasm-skills
python examples/build_your_agent.py
python templates/agent_template.py        # 骨架自带的冒烟
```

想**照着一步步自己写出一个智能体**（含实现、应用、真实效果），用 `demo/` 包：

```bash
python -m demo.run_all              # 一键跑完 6 步 + 汇总应用效果
python demo/step_01_minimal.py      # 或单步看每一环节
```

**手把手教程与分步 demo**：[`demo/README.md`](demo/README.md) ·
[`docs/BUILD-AGENT.md`](docs/BUILD-AGENT.md)

---

## 二、基座负责什么 / 不负责什么

| 基座负责 | 基座不负责 |
|---|---|
| ✅ 记忆写入 / 重要度淘汰 / 检索 | ❌ 具体某个智能体的人格与话术 |
| ✅ 情绪状态与渲染（有 torch 时接真人格模块） | ❌ 具体业务逻辑（用药提醒、选题策略…） |
| ✅ 动作选择（性格基线 + 反馈塑形） | ❌ 调用哪个大模型（**基座零 LLM 依赖**） |
| ✅ 状态落盘与跨进程恢复 | ❌ 具体智能体的测试与验收标准 |
| ✅ 档位检测与如实降级标注 | ❌ 替你把降级藏起来 |
| ✅ 技能包打包（两种归档形态） | ❌ 替你上传到平台 |

**基座不内置任何智能体**，这是刻意的：`python -m pasm_skills list` 在干净环境下
会显示 0 个智能体，并提示你装一个。

---

## 三、档位透明（永不隐藏降级）

| tier | 依赖 | 得到什么 |
|---|---|---|
| `light` | 无 | 纯内置：重要度淘汰 + 字面检索 + 性格/反馈加权 |
| `core` | 能 `import pasm.cognitive`（**不需要 torch**） | 真 `memory_layers`（分层记忆）+ `learning.LearningEngine` |
| `bionic` | 上面 + torch | 再加真情绪 / 人格模块 |

**三个档位下接口完全一致** —— 调用方不写分支，但 `agent.tier` 一定会如实告诉你现在在哪一档。

---

## 四、目录

```
pasm-skills/
├── pasm_skills/                 ★ 基座本体
│   ├── sdk/                     ★ SDK：BaseAgent（写智能体从这里开始）
│   │   └── base.py              记忆 / 情绪 / 动作 / 反馈 / 持久化 + 两个适配层
│   ├── agent.py                 框架：Agent 基类 / AgentResult / Finding / 注册表
│   ├── discovery.py             智能体发现（entry points / PASM_SKILLS_PATH）
│   ├── context.py               仓隔离探测（RepoContext）
│   ├── scenarios.py             场景仿真底座（解释器择优 / PRELUDE / 阈值判定）
│   ├── checks.py                核心契约检查工具箱
│   ├── build.py                 ★ 技能包打包库（两种归档形态）
│   └── cli.py                   pasm-skills 命令行
│
├── templates/                   ★ 脚手架：复制就能改
│   ├── agent_template.py        智能体骨架（自带冒烟）
│   └── SKILL.template.body.md   技能正文模板
│
├── examples/                    可跑示例（不依赖任何成品智能体）
│   └── build_your_agent.py      从零到落盘的完整走查
│
├── demo/                        ★ 手把手分步教程包：教你从零写一个智能体
│   ├── README.md                分步实现 + 应用 + 真实效果（从这里开始）
│   ├── agent.py                 完整版「学习陪伴·小墨」（可直接 import 用）
│   ├── step_01..06_*.py         6 个独立可跑的分步教学
│   ├── step_07_apply.py         实现后怎么接进 CLI / FastAPI / 游戏
│   └── run_all.py               一键跑完 6 步 + 汇总应用效果
│
├── skill/                       ★ 基座自己的技能正文
│   └── SKILL.authoring.body.md  「怎么写 PASM 智能体 + 打技能包」
│
├── tools/
│   └── build_skill.py           声明本仓技能 → 调用 pasm_skills.build
│
└── docs/
    ├── TUTORIAL.md              ★ 使用教程（先读这个）
    ├── BUILD-AGENT.md           ★ 手把手：从零做一个智能体
    ├── SKILL-FORMAT.md          ★ 技能包格式与两种归档形态
    ├── ARCHITECTURE.md          框架分层与设计取舍
    └── SERVER-NEEDS.md          服务器需求评估（结论：不需要）
```

---

## 五、命令行

```bash
python -m pasm_skills selftest        # 自检：SDK / 框架 / 发现机制（零依赖）
python -m pasm_skills list            # 已发现的智能体 + 三仓定位
python -m pasm_skills agents          # 只报告智能体从哪加载进来（排障）
python -m pasm_skills repos           # 只打印仓库定位
python -m pasm_skills run <name>      # 跑一个智能体
python -m pasm_skills run --all       # 跑全部已发现的
```

退出码：`0` 全部通过 / `1` 有 FAIL / `2` 用法错误 —— 可直接用于 CI。

---

## 六、让自己的智能体被基座发现

| 方式 | 适用 | 用法 |
|---|---|---|
| `PASM_SKILLS_PATH` | 本地开发最快 | 指向一个 `.py` 文件或目录 |
| `PASM_SKILLS_AGENT_MODULES` | 显式钉死模块 | 逗号分隔的模块名 |
| **entry points**（推荐） | 装成包后自动发现 | `[project.entry-points."pasm_skills.agents"]` |

```toml
[project.entry-points."pasm_skills.agents"]
my-agents = "my_pkg.agents"
```

三种都失败也不会报错 —— 基座照样能 `selftest` / `list`，只是智能体数为 0。
**基座不依赖任何智能体。**

---

## 七、安装

```bash
pip install pasm-skills        # 基座（零依赖，stdlib only）
pip install -e .               # 开发模式
pip install pasm-agents        # 想要现成智能体（依赖本基座）
```

## 八、本机配置（可选）

本机"带 torch 的那个解释器"往往在仓库外，所以配置也放**仓库外**。
在 `~/.pasm-skills/local.json` 写：

```json
{ "python": ["/path/to/python-with-torch", "%%HOME%%/venv/bin/python"] }
```

（`%%HOME%%` 是占位符；也支持 `PASM_LOCAL_CONF` 指定别的路径。）

- 找得到 → 场景跑 `bionic` / `core` 档；找不到 → 自动降级 `light` 并**在每条结论里标注**
- 建议指向**自带 site-packages 的 venv**：若环境改写了 `APPDATA`，Python 的 user site
  packages 会指向别处，装在 user site 的 torch 就会"时有时无"

优先级：`PASM_TORCH_PYTHON` → `PASM_PYTHON` → 本机配置 → 当前解释器 → 仓库内 venv → `PATH`。

## 九、许可证

MIT。技能包在部分平台需按平台要求标 `MIT-0`（比 MIT 更宽松，允许无署名使用）——
本仓的 `tools/build_skill.py` 里对两种形态分别处理，详见 `docs/SKILL-FORMAT.md`。
