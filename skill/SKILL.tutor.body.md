> 本文件是 **pasm-tutor 技能 SKILL.md 的正文部分**（不含 frontmatter）。
> `tools/build_skill.py` 会把它分别拼上两种归档形态的 frontmatter（`zip-root` / `slug-dir`），产出可直接上传的包。

# PASM 学习陪伴智能体（pasm-tutor）

给学生的陪伴式学习助手：**薄弱点定位 + 最弱优先选题 + 鼓励式对话 + 学情可机读导出**。
零 LLM 依赖、断网可用、状态可持久化。

```python
from pasm_agents import LearningTutor

t = LearningTutor(agent_id="xiaoya", persona={
    "name": "小雅", "grade": "五年级",
    "topics": ["分数加减", "面积计算", "行程问题", "鸡兔同笼"],
})

t.report("分数加减", 0.4)      # 报告一次作答得分（0~1）
t.report("分数加减", 0.5)
t.report("面积计算", 0.9)

print(t.pick_next())          # -> '行程问题'（最弱优先）
print(t.mastery("面积计算"))   # -> 0.27
print(t.chat("分数加减好难"))  # 鼓励 + 具体下一步
print(t.chat("我哪里不行"))    # 直接给出最弱项 + 掌握度
print(t.snapshot())           # 学情结构（纯 JSON，画像层可直接消费）
```

## 什么时候用

- 需要**按知识点追踪掌握度**，而不是只记总分；
- 需要**自适应选题**：总是推最该练的那个，而不是随机或顺序出题；
- 需要**鼓励式对话**而不是打击式反馈（"这一步你上次也栽了，我们换个讲法"）；
- 需要一份**机器可读的学情快照**，接进自己的画像 / 报表 / 家长端。

## 0. 铁律

1. **掌握度用 EMA 追踪**：`report(topic, score)` 做指数滑动平均
   （`新 = 旧*0.7 + 本次*0.3`），单次失手不会把掌握度打到谷底，连续失误才真正下探。
2. **选题可解释**：`pick_next()` 返回"当前掌握度最低的知识点"，
   同时给出理由 —— 不是黑箱推荐。
3. **回复必须鼓励式**：不说"你怎么又错了"，说"这块确实容易混，我们换个角度"。
4. **零 LLM 依赖**：讲解走模板 + 知识点状态，不调用外部大模型；断网可跑。
5. **学情可导出**：`snapshot()` 输出稳定结构的纯 JSON，
   **上层画像引擎可以直接消费**，不需要解析自然语言、也不需要伸手进内部字典。

## 1. 30 秒上手

```bash
git clone https://gitee.com/arronzheng/pasm-skills
cd pasm-skills
pip install -e .

pasm-agents demo tutor                 # 预置剧本（小雅 30 天 × 4 题）
pasm-agents run tutor --id=my_tutor    # 交互模式
pasm-agents inspect my_tutor           # 看落盘快照
```

## 2. persona 里必须有的东西

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | 学生称呼 |
| `grade` | 建议 | 年级，写进回复模板 |
| `topics` | ✅ | 知识点列表。**这张表就是你的课程大纲** |
| `tone` | 建议 | 语气（默认"温柔、耐心"） |

不传 `topics` 时用内置的 6 个五年级知识点：分数加减 / 面积计算 / 行程问题 /
鸡兔同笼 / 质因数分解 / 图形对称。

## 3. 掌握度与选题

```python
print(t.report("行程问题", 0.3))     # -> {'topic': '行程问题', 'new_mastery': 0.09}
print(t.report("行程问题", 0.35))    # -> {'topic': '行程问题', 'new_mastery': 0.168}

print(t.mastery("行程问题"))          # 0.168
print(t.pick_next())                 # '行程问题'（现在最低）
print(t.snapshot())
# {
#   "student": "小雅", "grade": "五年级",
#   "mastery": {"分数加减": 0.12, "面积计算": 0.27, "行程问题": 0.168, ...},
#   "weakest": "图形对称",
#   "average": 0.145,
#   "history_size": 3,
#   "tier": "light"
# }
```

> `pick_next()` 有 **20% 的抖动**：80% 概率给最弱项，20% 随机选一个防"刷同一个知识点"。
> 要严格确定性的选题，直接用 `snapshot()["weakest"]`。

**推荐阈值**（由调用方决定，本技能只提供数值与排序）：
掌握度 < 0.5 视为薄弱，0.5~0.8 巩固，> 0.8 可推进新内容。

## 4. 对话

```python
print(t.chat("分数加减好难"))     # 共情 + 具体下一步（不是空洞鼓励）
print(t.chat("我哪里不行"))       # 直接列最弱项 + 掌握度数字
print(t.chat("我会了"))           # 鼓励 + 推两道巩固
```

回复模板走的是"**承认难度 + 给最小可行动作**"，避免"加油你可以的"这类无效安慰。
渲染集中在 `_render_reply(text, facts, mood)`，子类可覆盖。

## 5. 用错题记忆做横向关联

每次 `report` 会顺带写一条记忆：得分 < 0.6 记 `salience=3` + `category="错题"`，
否则 `salience=2` + `category="进步"`。所以它能做"这道题和上次那道错的是一类"：

```python
t.observe("上次在'相遇问题'上把速度和当成路程了",
          tags=["错题", "行程问题"], salience=3, category="错题")
print(t.chat("行程问题又不会了"))   # 能召回上次那条错题
```

若 PASM 核心可用（`tier=core/bionic`），`report` 还会把分数转成强化量
（`delta = score - 0.5`）驱动核心的学习层。

## 6. 交互模式

```bash
pasm-agents run tutor --id=my_tutor --persona-file=personas/xiaoya.json
```

直接打字对话。可用命令：

| 命令 | 作用 |
|---|---|
| `report <知识点> <0~1 分数>` | 记录一次作答，返回新掌握度 |
| `next` | 看下一个该练的知识点 |
| `snapshot` | 导出学情 JSON |
| `mood` | 看当前情绪 |
| `act` | 执行一个动作 |
| `observe <文本>` | 手动写一条记忆 |
| `feedback <praise\|poke\|scold> [动作]` | 给反馈 |
| `quit` | 退出并 save |

## 7. 档位透明

| tier | 含义 | 何时启用 |
|---|---|---|
| `bionic` | 仿生：完整 PASM 核心 + emotion 模块（需 torch） | `pip install pasm-skills[torch]` |
| `core`    | 完整：PASM 核心（memory + learning，无 torch） | `PASM_PYTHON` 指向带核心的 Python |
| `light`   | 轻量：纯内置（重要度淘汰 + 字面检索 + softmax 权重） | 任何机器 |

## 8. 已知短板（如实说明）

- **没有遗忘曲线**：掌握度只增不减，停练的知识点**不会自动衰减**。
  `study-tutor` 验证智能体用"前 5 天练、之后彻底停练"的场景测过，`decay_works = 0`。
  需要衰减的话，调用方可以定期 `report(topic, 更低的分)` 手动拉低 —— 但那是绕路，不是内置能力。
- **跨表述检索是字面匹配**：`memvec` 是字符 n-gram 哈希，不是语义模型。
  换个说法问同一个知识点，未必召回得到。

这两条改的是**产品行为**而非缺陷，所以本仓选择如实标注、不偷偷糊上去。

## 9. 与验证层的关系

`pasm_skills/` 里的 `study-tutor` 是**专门验证这类教学智能体的智能体**：
跑 30 天 × 4 题 × 6 个知识点，测学情结构对不对、有没有遗忘机制、错题关联能不能召回。
`snapshot()` 的形状与它定义的学情结构一致，所以**上层画像层可以直接复用同一套字段**。

## 10. 相关技能

- `pasm-npc` —— 游戏 NPC 智能体
- `pasm-companion` —— 老人陪伴智能体
- `pasm-longterm-verify` —— 验证层入口：回答"跑久了还是好的吗"
