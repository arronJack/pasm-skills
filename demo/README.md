# PASM 智能体 Demo · 手把手从零写一个智能体

> **目标**：照着这份 demo，你能在 30 分钟内写出**第一个能记忆、有情绪、能被反馈塑形、能落盘**的智能体，
> 知道**写出来之后怎么接进真实产品**，并且看到**真实跑出来的应用效果**。
>
> 本 demo 是 [`pasm-skills`](../README.md) 基座的**教学包**：基座只提供能力，不提供智能体；
> 这里手把手教你**用基座造出一个智能体**。

---

## 先搞懂：PASM 是什么 · 为什么用 pasm-skills 写智能体 · 优劣势

> 这一步不写代码，先建立**选型认知**——知道自己为什么选它、它能给你什么、边界在哪，
> 后面 7 步写起来才会"知其所以然"。想直接动手的，可跳到 [§0 环境准备](#0-环境准备)。

### 1）PASM 与 pasm-skills 的关系

PASM（认知智能体引擎）是一套"会记忆、有情绪、能被反馈塑形、能长期陪伴"的认知引擎。
它分三层交付：

| 层 | 仓库 | 给谁 | 干什么 |
|---|---|---|---|
| 核心引擎 | `PASM`（私有） | 桌面应用 / 引擎开发者 | 认知层 + 模块 + 桌面端（PySide6 + Ollama + TTS + 高德地图） |
| **基座** | **`pasm-skills`（本仓，MIT）** | **每一个想写智能体的人** | `BaseAgent` SDK + 框架 + 打包工具（**零依赖**） |
| 成品智能体 | `pasm-agents`（公开） | 直接拿来用的人 | 游戏 NPC / 老人陪伴 / 学习陪伴等现成智能体 |

一句话：**`PASM` 是引擎，`pasm-skills` 把引擎拆成普通人能用的积木，`pasm-agents` 是用积木搭好的成品。**
你要"造自己的智能体"，用的就是本仓 `pasm-skills`。

### 2）pasm-skills 的核心特性

| 特性 | 说明 | 你得到的好处 |
|---|---|---|
| **认知原语开箱即用** | 记忆 / 情绪 / 动作 / 反馈 / 持久化全部由 `BaseAgent` 包办 | 只写 2 个钩子就能有"灵魂" |
| **三档透明降级** | `light`(纯内置) / `core`(分层记忆) / `bionic`(+真人格模块) | 拿到核心更强，没有也能跑；`tier` 永远如实标注 |
| **零依赖** | 不需要 torch、不需要 API key、不需要服务器 | 任何机器、`pip install` 即跑 |
| **反馈塑形（强化式）** | 用 `feedback()` 夸/凶一个动作，行为被学习改变 | 智能体"越用越像你想要的" |
| **跨进程持久化** | 自动落盘 `~/.pasm-agents/<id>/`，再实例化状态全在 | 长期陪伴 / 生产级不怕重启 |
| **结构化学情 / 状态快照** | `state.notes` + `snapshot()` 机读出口 | 外部系统能稳定读取智能体内部状态 |
| **成长阶段解锁** | 动作池随 `growth_stage` 动态变化 | 智能体"越用越能干" |
| **多形态集成** | 智能体是普通 Python 对象，塞进 CLI / FastAPI / 游戏 / 桌面 | 一行 `import` 就能接进你的产品 |
| **技能包打包 + 发现** | 写→测→打包→发布一条龙（`build.py`） | 写好的智能体能发布给别人用 |

### 3）为什么用 pasm-skills 创建智能体（而不是从零写 / 直接用 LLM）

- **vs 从零造轮**：记忆淘汰、情绪渲染、动作采样、反馈加权、落盘恢复……这些"认知基础设施"你自己写要几百行还易错。基座一行 `BaseAgent` 全给，你只填"它能做什么 + 它怎么回"。
- **vs 直接调 LLM API**：LLM 只是"嘴"——没有记忆、没有性格、不会因为你夸它就多讲题。pasm-skills 给的是"会记住你、有情绪、能被塑形的主体"，LLM 只是可插拔的渲染后端（`_render_reply` 里接 DeepSeek / 本地模型都行）。
- **vs 纯编排框架（LangChain / AutoGPT 类）**：那些偏"工具链编排"，PASM 偏"认知与行为塑形"——它关心智能体**本身**有没有记忆、情绪、成长，而不是怎么串外部工具。
- **透明可复现**：档位永远如实告诉你现在有多强；`light` 档 `seed` 固定可复现，教学和排障都稳。
- **生产友好**：持久化 + 发现机制 + 打包 CLI，写出来的东西能直接进产品、能发布。

### 4）优势 / 劣势 / 适用边界（说人话）

**✅ 优势**
- 上手极快：30 分钟写出第一个"会记忆、有情绪、能落盘"的智能体。
- 零依赖、可离线、可复现（固定 seed）。
- 能力语义跨档一致：降级只降"精度"，不降"能力"。
- 认知原语通用：不止对话机器人，NPC / 客服 / 知识库 / 评测后端都能用。
- 行为可塑形、状态可持久化、可一键打包发布。

**⚠️ 劣势 / 已知边界（来自引擎自述，诚实列出）**
- **检索是字面匹配**（light / core 档）：换种说法的同一句话可能搜不到，命中率 ≈ 0.5。要语义级，得在 `_render_reply` 里自己接 LLM / 向量检索。
- **学习层暂无遗忘曲线**：停练的知识点不衰减，长期学情可能失真（教育 / 老人场景要注意）。
- **人格长期可能饱和**：bionic 档相处极久后情绪/性格可能钉死在 ±1，像"坏掉"。
- **基座零 LLM**：语义理解、文本生成不内置，需你自己接模型。
- **多模态未直接暴露**：语音 / 图像 currently 要你自己接进 `BaseAgent`。
- **目前 Python-only**：没有 JS / Go SDK。
- **高级档需 torch 解释器**：`core` / `bionic` 的部分能力需要带 torch 的环境（但 `light` 档完全不需要）。

> 这些不是"缺陷清单"，而是**选型时要知道的边界**。绝大多数"造一个会记忆、有情绪、能长期陪伴的智能体"的需求，`light` 档已经够用；要语义 / 多模态 / 真人格，按需往上接即可。

### 5）一句话选型

> 想要一个**真正有记忆、有情绪、能陪你长期成长、还能发布给别人用**的智能体 → 用 `pasm-skills`。
> 只想临时让 LLM 串几个工具 → 直接用 LLM / 编排框架更轻。

---

我们要做出的东西：一个**学习陪伴智能体「小墨」**——会记住学生的薄弱知识点、被夸了更爱讲题、
有情绪（累了语气会变软）、能跟踪每个知识点的掌握度、并随"成长阶段"解锁更多功能。

---

## 0. 环境准备

```bash
# 方式 A：已发布安装
pip install pasm-skills

# 方式 B：从源码（本仓库）
git clone https://gitee.com/arronzheng/pasm-skills
cd pasm-skills
pip install -e .
```

**零依赖**：不需要 torch、不需要 PASM 核心、不需要 API key、不需要服务器。
拿不到核心时自动降级到 `light` 档，并在 `tier` 如实标注（永不隐藏）。

先确认基座没坏：

```bash
python -m pasm_skills selftest     # 15 项自检，零依赖
python -m pasm_skills list         # 基座不内置智能体，这里显示 0 个（正常）
```

---

## 1. 目录（本 demo 包）

```
demo/
├── README.md              ← 你正在读（分步教程 + 应用 + 效果）
├── agent.py               ★ 完整版「小墨」：6 步演变后的最终形态（可直接 import 用）
├── step_01_minimal.py     第 1 步：最小智能体（两个钩子）
├── step_02_memory.py      第 2 步：+ 记忆（重要度）
├── step_03_feedback.py    第 3 步：+ 反馈塑形（行为被学习改变）
├── step_04_emotion.py     第 4 步：+ 情绪（mood 影响语气）
├── step_05_state.py       第 5 步：+ 结构化学情（state.notes + snapshot）
├── step_06_growth.py      第 6 步：+ 成长（阶段解锁动作）
├── step_07_apply.py       第 7 步：应用（CLI / FastAPI / 游戏循环 + 可跑会话）
└── run_all.py             ★ 一键跑完 6 步 + 汇总应用效果
```

每一步都是**独立可运行**的 `.py` 文件；想一口气看全貌：

```bash
python -m demo.run_all          # 或 python demo/run_all.py
```

---

## 2. 第 1 步：最小智能体（只写两个钩子）

> 文件：`demo/step_01_minimal.py`

`BaseAgent` 只要求你实现**两个钩子**：`action_pool()`（能做什么）和
`_render_reply(text, facts, mood)`（怎么回）。其余全由基座包办。

```python
from pasm_skills.sdk import BaseAgent

class StudyBuddy(BaseAgent):
    def action_pool(self):
        return ["greet", "teach", "peek", "rest"]

    def _render_reply(self, text, facts, mood):
        name = self.persona.get("name", "小墨")
        return f"{name}：你好呀，我是你的学习小老师～"

a = StudyBuddy(agent_id="owner",
               persona={"name": "小墨", "temper": 0.6, "energy": 0.4})
print(a.tier)        # 'light' / 'core' / 'bionic'
print(a.act())       # 从动作池里挑一个（性格基线驱动）
print(a.chat("你好"))
a.save()             # ~/.pasm-agents/owner/
```

运行 `python demo/step_01_minimal.py`，你会看到（本机无核心，跑在 `light` 档）：

```
tier  = light （light=纯内置 / core=PASM核心 / bionic=+情绪模块）
act() = teach    # 从动作池里挑一个（性格基线驱动）
chat()= 小墨：你好呀，我是你的学习小老师～
save() 已落盘到: C:\Users\...\AppData\Local\Temp\...
```

**要点**：就这两个钩子。记忆淘汰、情绪、动作采样、落盘——基座都做好了。

---

## 3. 第 2 步：加记忆（重要度决定谁活下来）

> 文件：`demo/step_02_memory.py`

```python
a.observe("小雅每周三都卡在行程问题", brief="画图就懂",
          tags=["行程问题", "弱点"], salience=4, category="学情")
a.observe("上次月考面积计算满分", tags=["面积计算"], salience=3, category="学情")
a.observe("今天下雨，没去图书馆")                  # 默认 salience=1，最先被淘汰

print(a.recall("行程问题", k=3))   # 字面匹配：tags 里带「行程问题」的就命中
```

真实运行输出：

```
首次启动自动写入的初始记忆： ['今天开始当你的学习小老师']
recall('行程问题') -> ['小雅每周三都卡在行程问题', '上次月考面积计算满分', '今天下雨没去图书馆']
recall('面积')      -> ['上次月考面积计算满分', '小雅每周三都卡在行程问题', '今天下雨没去图书馆']
```

| 概念 | 说明 |
|---|---|
| `salience` | `1` 日常 / `3` 值得记 / `5` 关键（里程碑、安全事实）。容量上限 **200 条**，触顶按 `(salience, 新旧)` 淘汰——**重要度优先** |
| 检索 | **字面匹配**（light / core 都一样）。想让某句话被搜到，就在 `tags` 里带人们会说的词 |

---

## 4. 第 3 步：加反馈塑形（行为会被学习改变）

> 文件：`demo/step_03_feedback.py`

```python
a.feedback("praise", action="teach")   # +0.3  夸「讲题」
a.feedback("scold",  action="peek")    # -0.3  凶「偷看」
```

⚠️ **一定要传 `action`**：不传的话反馈会作用在"当前最偏好的动作"上，偏好越高越加码，
长期行为会极端化。

真实运行（seed=0 可复现，反馈前/后各采样 400 次）：

```
动作    反馈前 → 反馈后（占比，seed=0 可复现）
  greet   22.5% →   0.0%
  teach   28.2% → 100.0%
  peek    23.2% →   0.0%
  rest    26.0% →   0.0%
结论：被夸的 teach 变多、被凶的 peek 变少 —— 智能体真的「学到了」。
```

> **为什么 greet / rest 也掉到 0%？** 动作选择是 **softmax**（`得分 = 性格基线 + 学习权重` 再归一化）。
> 把 `teach` 大幅加码后，它会主导分布，其它动作相对被压低。这是框架的真实语义——
> **想保留多个动作并存，就分散夸多个动作**（例如同时 `praise` greet 和 teach）。

---

## 5. 第 4 步：加情绪（mood 影响语气）

> 文件：`demo/step_04_emotion.py`

```python
print(a.mood)                     # float ∈ [-1, 1]（属性，不加括号）
a.feel("学生今天骂了人", valence=-0.8)   # 注入一次情绪事件
print(a.chat("我们做题吧"))       # 低落时语气变软
```

真实运行：

```
mood（初始）      = 0.0
chat（开心时）    = 小墨：好呀，我们继续！
mood（受委屈后）  = -0.08
chat（低落时）    = 小墨：（有点累）这道题我们慢慢来，不急。
```

`mood` 会被自动传进 `_render_reply(text, facts, mood)`，所以"同一句话高兴/生气说得不一样"是**自然发生**的，不用你写 if-else。
有 torch 时接真人格模块（`tier=bionic`），否则用内置回退——**接口完全一致**。

---

## 6. 第 5 步：加结构化学情（state.notes + snapshot）

> 文件：`demo/step_05_state.py`

需要按知识点记分这类结构化数据，放 `self.state.notes`（随 `agent_state.json` 落盘，不用另开文件）：

```python
def report(self, topic, score):
    ks = self.state.notes.setdefault("knowledge_state", {})
    prev = ks.get(topic, 0.0)
    ks[topic] = round(prev * 0.7 + score * 0.3, 3)   # EMA 平滑
    return {"topic": topic, "new_mastery": ks[topic]}

def snapshot(self):        # 给外部稳定的机读出口，别让调用方读 notes
    ks = self.state.notes.get("knowledge_state") or {}
    return {"mastery": ks, "weakest": min(ks, key=ks.get) if ks else None,
            "average": ..., "tier": self.tier}
```

真实运行：

```
report: {'topic': '分数加减', 'new_mastery': 0.12}
report: {'topic': '面积计算', 'new_mastery': 0.27}
report: {'topic': '行程问题', 'new_mastery': 0.06}
mastery('行程问题') = 0.06
snapshot() = {'mastery': {'分数加减': 0.12, '面积计算': 0.27, '行程问题': 0.06},
              'weakest': '行程问题', 'average': 0.15, 'tier': 'light'}
```

**原则**：外部要读的，给一个 `snapshot()`；`state.notes` 是内部状态，别让调用方伸手进去。

---

## 7. 第 6 步：加成长（阶段解锁动作）

> 文件：`demo/step_06_growth.py`

动作池不是写死的——阶段越高，能做的越多：

```python
ACTS = {0: ["greet","teach","peek","rest"],
        1: [... ,"quiz","give"],
        2: [... ,"report"]}
def action_pool(self):
    stage = min(self.state.growth_stage, max(self.ACTS))
    return list(self.ACTS[stage])
```

真实运行：

```
阶段 0 动作池： ['greet', 'teach', 'peek', 'rest']
阶段 1 动作池： ['greet', 'teach', 'peek', 'rest', 'quiz', 'give']
阶段 2 动作池： ['greet', 'teach', 'peek', 'rest', 'quiz', 'give', 'report']
```

基座的 `act()` 会自动从"当前阶段解锁的池子"里选动作。

---

## 8. 第 7 步：实现之后怎么用（应用）

> 文件：`demo/step_07_apply.py`（可运行）

智能体是**普通 Python 对象**，可以塞进任何东西：Web 服务、游戏、桌面、定时任务。

### 8.1 一段真实对话（应用效果先睹为快）

```
--- 一段真实对话（学习陪伴·小墨）---
  小明: 在吗
  小墨: 小墨：我记得你说过「小明说行程问题老是错」，我们再练练？
  小明: 我今天行程问题又错了
  小墨: 小墨：我记得你说过「小明说行程问题老是错」，我们再练练？
  小明: 面积计算我好像会了
  小墨: 小墨：我记得你说过「对话：我今天行程问题又错了。」，我们再练练？
  学情快照: {'mastery': {'行程问题': 0.09, '面积计算': 0.27}, 'weakest': '行程问题', ...}
```

（注：`light` 档是**字面检索**，所以"面积计算我好像会了"这种否定句也会被「面积计算」这个关键词命中——
要语义级理解，在 `_render_reply` 里接一个 LLM 即可，基座不拦。）

### 8.2 跨进程恢复

同一 `agent_id` 再实例化，记忆/学情都还在（落盘在 `~/.pasm-agents/<id>/`）：

```
新实例 interactions = 3 （记忆已恢复）
新实例 weakest      = 行程问题
```

### 8.3 三种集成骨架（复制即用）

```python
# ① 命令行 / 桌面交互
def loop(agent_id, persona):
    b = StudyBuddy(agent_id=agent_id, persona=persona)   # 自动恢复状态
    while True:
        text = input("你: ")
        if text.strip().lower() in ("quit", "exit"):
            b.save(); break
        print("小墨:", b.chat(text))

# ② FastAPI（Web 服务）
from fastapi import FastAPI
app = FastAPI()
@app.post("/chat")
def chat(agent_id: str, text: str, persona: dict):
    b = StudyBuddy(agent_id=agent_id, persona=persona)
    return {"reply": b.chat(text), "tier": b.tier, "snapshot": b.snapshot()}

# ③ 游戏 / 模拟循环
def tick(npc, world_event: str):
    npc.observe(world_event, tags=["世界"], salience=3)
    play_animation(npc.act())      # 选一个动作并播放
```

---

## 9. 应用效果汇总（真实跑出来的数字）

跑 `python -m demo.run_all` 会自动输出这份对照。`light` 档（本机无核心）实测：

| 效果 | 证据 |
|---|---|
| **① 反馈塑形**：夸的动作主导，凶的动作消失 | `teach` 28.2% → **100%**；`peek` 23.2% → **0%**（seed=0 可复现） |
| **② 记忆检索**：关键学情能被召回 | `recall("行程问题")` 命中「小雅每周三都卡在行程问题」 |
| **③ 持久化恢复**：换进程记忆/学情都在 | 新实例 `interactions = 3`，`weakest = 行程问题` |
| **④ 学情跟踪**：掌握度被平滑记录 | `snapshot = {行程问题:0.09, 面积计算:0.27, weakest:行程问题}` |

> 想看 `core` / `bionic` 档的效果：装好带 torch 的解释器，设
> `PASM_TORCH_PYTHON=/path/to/python`，再跑 `run_all`——检索会变成真分层记忆、
> 情绪接真人格模块，但**上面四件事的结论方向一致**（降级永不改变能力语义）。

---

## 10. 打包与发布（呼应基座工作流）

写出智能体后，把它打成平台可上传的技能包（两种归档形态），见基座
[`docs/BUILD-AGENT.md` §十](../docs/BUILD-AGENT.md) 与 [`docs/SKILL-FORMAT.md`](../docs/SKILL-FORMAT.md)：

```bash
# 在你的智能体仓里：
#   1) skill/SKILL.<name>.body.md   （复制 templates/SKILL.template.body.md）
#   2) tools/build_skill.py         （声明 SKILLS 列表，import pasm_skills.build）
python tools/build_skill.py --zip --clean
# 产物：<repo>-dist/{zip-root,slug-dir}/<name>/SKILL.md + <name>-<ver>.zip
```

让基座发现它：`PASM_SKILLS_PATH=./my_agents python -m pasm_skills list`，或正式发布时
在 `pyproject.toml` 声明 entry point `[project.entry-points."pasm_skills.agents"]`。

---

## 11. 常见问题

| 症状 | 原因 / 处理 |
|---|---|
| `act()` 报 `NotImplementedError` | 没实现 `action_pool` → 见第 1 步 |
| `chat()` 报 `NotImplementedError` | 没实现 `_render_reply` → 见第 1 步 |
| `a.mood()` 报 `'float' object is not callable` | `mood` 是**属性** → 写 `a.mood` |
| 反馈后行为没变化 | `feedback` 没传 `action=` → 传上（见第 3 步） |
| 关键记忆被挤掉 | 没用 `salience=5`（或至少 4）→ 见第 2 步 |
| 全部结论都是 `light` 档 | 没找到带 torch 的解释器 → 设 `PASM_TORCH_PYTHON` |

---

## 12. 下一步

- 想看**真实产品智能体**长什么样 → 读 [`pasm-agents`](https://gitee.com/arronzheng/pasm-agents) 源码
  （游戏 NPC / 老人陪伴 / 学习陪伴 = 3 产品 + 7 验证，每个文件夹里实现 + 说明 + 可跑示例）
- 想改**基座本身** → [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
- 想写**验证智能体**（给核心做长期体检）→ 基座 [`docs/TUTORIAL.md` §5](../docs/TUTORIAL.md)
