> 本文件是 **pasm-agents 技能 SKILL.md 的正文部分**（不含 frontmatter）。
> `tools/build_skill.py` 会把它分别拼上两种归档形态的 frontmatter（`zip-root` / `slug-dir`），产出可直接上传的包。

# PASM 产品智能体（pasm-agents）

基于 PASM 引擎的**可立即装载**的智能体。零 LLM 依赖、断网可用、状态可持久化。

三个开箱即用的产品级智能体：

- **NpcAgent** —— 游戏 NPC：性格 + 记忆 + 情绪 + 成长动作
- **ElderlyCompanion** —— 老人陪伴：关键事实 100% 记忆 + 危机自动升级
- **LearningTutor** —— 学习陪伴：薄弱点定位 + 自适应选题 + 进度跟踪

每个都基于同一个 `BaseAgent`，差异只在 persona、动作池、聊天模板。

## 什么时候用

- 给游戏加一个**有记忆有情感的 NPC**（不是写死的台词表，是真的能记住玩家、情绪会变化）；
- 给独居老人做**关键事实 + 用药 + 危机**陪伴，关键事实永不丢，危机自动升级；
- 给学生做**薄弱点定位 + 自适应选题**；
- 想在自己产品里**接入 PASM 引擎能力**，但不想从零搭记忆/情绪/学习层。

## 0. 铁律

1. **零 LLM 依赖**：聊天是纯模板 + 检索 + 情绪渲染，不调用任何外部大模型；
   断网/无显卡/无 API key 都能跑。
2. **PASM 核心真接入**：能用 `pasm.cognitive.memory_layers` / `learning` 时优先用；
   找不到核心时降级到内置轻量适配，并在 `tier` 字段写明档位，**永不隐藏降级**。
3. **关键事实永不丢**：陪伴场景下 `salience=5` 标记的关键事实
   （用药/过敏/家人）走"标签直查"路径，命中率 100%。
4. **反馈必须能指定动作**：`feedback(kind, action=)`，否则长期下来行为分布会被推到极端
   —— 这正是 `npc-lifelong` 验证智能体压出的产品级要求。
5. **持久化开箱即用**：每个 agent 落盘到 `~/.pasm-agents/<agent_id>/`，
   跨进程加载自动恢复上次状态。

## 1. 30 秒上手

```bash
git clone https://gitee.com/arronzheng/pasm-skills
cd pasm-skills
pip install -e .

# 三类智能体的预置剧本 —— 立刻看到效果
pasm-agents demo npc
pasm-agents demo companion
pasm-agents demo tutor
```

## 2. 在代码里使用

### 游戏 NPC

```python
from pasm_agents import NpcAgent

npc = NpcAgent(agent_id="herbalist", persona={
    "name": "陈伯", "role": "河边摆摊的草药老头",
    "temper": 0.55, "energy": 0.40, "play": 0.30,
    "tone": "慢悠悠、爱讲道理",
})

npc.observe("玩家第一次来买跌打药", salience=5,
            tags=["玩家", "救命"], category="重大")

print(npc.act())                  # 'wave' / 'talk' / 'peek' / ...
print(npc.chat("你叫什么名字"))   # 自我描述
print(npc.chat("有跌打药吗"))     # 召回重要记忆

npc.feedback("praise", action="talk")   # 显式夸"talk"
npc.save()                       # ~/.pasm-agents/herbalist/
```

### 老人陪伴

```python
from pasm_agents import ElderlyCompanion

comp = ElderlyCompanion(agent_id="chenxiulan", persona={
    "name": "陈秀兰", "age": 78,
    "tone": "慢、温和",
    "key_facts": [
        {"label": "用药", "content": "每天早 8 点吃降压药络活喜 5mg"},
        {"label": "过敏", "content": "青霉素过敏"},
        {"label": "家人", "content": "女儿在深圳，每周日来电话"},
        {"label": "本人", "content": "78 岁，独居"},
    ],
    "emergency_contact": {"name": "女儿小敏", "phone": "13900000000"},
    "medication_schedule": [{"name": "络活喜", "dose": "5mg", "hour": 8}],
})

print(comp.chat("我吃什么药"))               # 关键事实直查 → 100% 命中
print(comp.detect_crisis("卫生间滑倒"))      # ['摔倒/外伤']
print(comp.escalate("卫生间滑倒"))           # 写入紧急记忆 + 返回升级信息

# 用药提醒
for med in comp.due_medication(now_hour=8):
    print(f"⏰ 该吃 {med['name']} {med['dose']}")
```

### 学习陪伴

```python
from pasm_agents import LearningTutor

t = LearningTutor(agent_id="xiaoya", persona={
    "name": "小雅", "grade": "五年级",
    "topics": ["分数加减", "面积计算", "行程问题", "鸡兔同笼"],
})

t.report("分数加减", 0.4)     # 报告作答分数
t.report("分数加减", 0.5)
t.report("面积计算", 0.9)

print(t.pick_next())          # -> '分数加减'（最弱优先）
print(t.chat("分数加减好难")) # 鼓励 + 具体下一步
print(t.chat("我哪里不行"))   # 直接给出最弱项 + 掌握度

t.save()
```

## 3. 交互模式

```bash
pasm-agents run npc --id=my_herbalist --persona-file=personas/herbalist.json
pasm-agents run companion --id=my_companion
pasm-agents run tutor --id=my_tutor
```

进入交互模式后输入直接对话；`act` 看动作、`mood` 看情绪、
`feedback praise talk` 给反馈、`quit` 退出并 save。

## 4. 档位透明

每个 agent 的 `tier` 字段如实写明当前档位：

| tier | 含义 | 何时启用 |
|---|---|---|
| `bionic` | 仿生：完整 PASM 核心 + emotion 模块（需 torch） | `pip install pasm-skills[torch]` |
| `core`    | 完整：PASM 核心（memory + learning，无 torch） | `PASM_PYTHON` 指向带核心的 Python |
| `light`   | 轻量：纯内置（重要度淘汰 + 字面检索 + softmax 权重） | 任何机器 |

每个 agent 落盘 JSON 都有 `tier` 字段，调用方一眼就能判断。

## 5. 写你自己的 Agent

子类化 `BaseAgent`：

```python
from pasm_agents import BaseAgent

class MyAgent(BaseAgent):
    def _render_reply(self, text, facts, mood):
        # 基于检索到的事实 + 当前情绪渲染回复
        ...
    def action_pool(self):
        return ["say_hi", "think", "rest"]

# 用起来
a = MyAgent(agent_id="mine", persona={"name": "我的 Agent"})
a.observe("今天天气不错")
print(a.act())
```

## 6. 与验证层的关系

本仓库还有一个 `pasm_skills/` 包，里面是 7 个**验证智能体**
（`core-verifier` / `parity-guard` / `regression` / `npc-lifelong` /
`companion-elderly` / `study-tutor` / `soak-longrun`）——
它们**反向**给产品层兜底：

- 验证智能体压出的「同分排序崩溃」已被修进 `BaseAgent._CoreAdapter`；
- 「容量淘汰无重要度」已被产品层用 `salience=5` 解决；
- 「反馈无法指定动作」已被产品层 `feedback(action=)` 解决；
- 「关键事实检索 100% 命中」是 `companion-elderly` 验证器的 FAIL 级要求，
  `ElderlyCompanion._find_fact` 走的就是这条直查路径。

要查最新压出的问题清单，看 `docs/AGENTS.md`。

## 7. 安装

```bash
# 纯产品层（无 torch，tier=light）
pip install pasm-skills

# 完整档位（带 torch，tier=core/bionic）
pip install pasm-skills[torch]

# 开发模式
git clone https://gitee.com/arronzheng/pasm-skills
cd pasm-skills
pip install -e .
```

## 8. 相关技能

- `pasm-longterm-verify` —— 验证层入口（已发布到技能平台与技能市场）
- `pasm-agents` —— 本技能
- `pasm-release-pipeline` —— PASM Studio 桌面版打包发版
- `pasm-repo-persistence` —— PASM 五仓落盘与同步