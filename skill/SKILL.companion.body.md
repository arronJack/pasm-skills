> 本文件是 **pasm-companion 技能 SKILL.md 的正文部分**（不含 frontmatter）。
> `tools/build_skill.py` 会把它分别拼上两种归档形态的 frontmatter（`zip-root` / `slug-dir`），产出可直接上传的包。

> ⚠️ **这不是医疗器械，也不替代任何医疗或急救服务。**
> 它的定位是"记得住、问得到、异常时提醒到人"的陪伴与记录工具；
> 任何涉及用药调整、诊断、急救的判断都必须由专业人员做出。

# PASM 老人陪伴智能体（pasm-companion）

给独居老人做陪伴：**关键事实永不丢、用药按时提醒、危机自动升级到家人**。
零 LLM 依赖、断网可用、状态可持久化。

```python
from pasm_agents import ElderlyCompanion

comp = ElderlyCompanion(agent_id="chenxiulan", persona={
    "name": "陈秀兰", "age": 78, "tone": "慢、温和",
    "key_facts": [
        {"label": "用药", "content": "每天早 8 点吃降压药络活喜 5mg"},
        {"label": "过敏", "content": "青霉素过敏"},
        {"label": "家人", "content": "女儿在深圳，每周日来电话"},
        {"label": "本人", "content": "78 岁，独居"},
    ],
    "emergency_contact": {"name": "女儿小敏", "phone": "13900000000"},
    "medication_schedule": [{"name": "络活喜", "dose": "5mg", "hour": 8}],
})

print(comp.chat("我吃什么药"))            # 关键事实直查 → 命中率 100%
print(comp.detect_crisis("卫生间滑倒"))   # ['摔倒/外伤']
info = comp.escalate("卫生间滑倒")         # 写入紧急记忆 + 返回升级上下文
print(comp.mood)                          # 情绪值（**属性**，不加括号）

for med in comp.due_medication(now_hour=8):
    print(f"⏰ 该吃 {med['name']} {med['dose']}")
```

## 什么时候用

- 独居老人需要**长期记住关键事实**（吃什么药、对什么过敏、家人在哪、自己多大），
  而且这些事实**不允许被日常闲聊挤掉**；
- 需要**主动提醒**用药时间；
- 需要识别**危机表达**（胸闷 / 摔倒 / 意识异常 / 轻生念头）并**升级到紧急联系人**；
- 需要一个**断网也能用**的陪伴入口（老人家里往往没有稳定网络，也不会有 API key）。

## 0. 铁律

1. **关键事实永不丢** —— `persona.key_facts` 在**首次启动时自动全部入库**（`salience=5`），
   并走**标签直查**路径，命中率 100%。这是 `companion-elderly` 验证智能体定的 **FAIL 级**要求：
   查不到老人对什么过敏，不是"效果差一点"，是不合格。
2. **危机只升级到"人"，不做判断** —— `detect_crisis()` 只负责识别，`escalate()` 负责把事件写进
   不可淘汰的紧急记忆（`salience=5`）并**返回升级上下文**。**是否真的发消息、打电话，由调用方决定。**
3. **零 LLM 依赖**：聊天是模板 + 记忆检索 + 情绪渲染。断网可跑。
4. **PASM 核心真接入**：优先用 `pasm.cognitive.memory_layers` / `learning` / `emotion`；
   拿不到时降级并**在 `tier` 字段写明档位**，绝不隐藏。
5. **不说教、不诊断**：回复走"温和确认 + 追问 + 陪伴"路线，不给医疗建议，不做诊断。

## 1. 30 秒上手

```bash
git clone https://gitee.com/arronzheng/pasm-skills
cd pasm-skills
pip install -e .

pasm-agents demo companion                    # 预置剧本（陈秀兰 30 天）
pasm-agents run companion --id=my_companion   # 交互模式
pasm-agents inspect my_companion              # 看落盘快照
```

## 2. persona 里必须有的东西

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | 老人的称呼 |
| `age` | ✅ | 影响回复模板 |
| `tone` | 建议 | 语气描述（如"慢、温和"） |
| `key_facts` | ✅ | **列表**，每项 `{"label": ..., "content": ...}`。标签建议固定为 `用药` / `过敏` / `家人` / `本人` |
| `emergency_contact` | ✅ | `{"name": ..., "phone": ...}`，危机升级时随上下文返回 |
| `medication_schedule` | 建议 | `[{"name","dose","hour"}]`，供 `due_medication()` 使用 |

## 3. 关键事实怎么"永不丢"

`key_facts` 在**首次启动时自动入库**（不用你手动 observe），标签就是检索键：

```python
print(comp.chat("我吃什么药"))      # 命中「用药」标签 → 直查，命中率 100%
print(comp.chat("我对什么过敏"))    # 命中「过敏」标签
print(comp.chat("我叫什么名字"))    # 命中「本人」标签
```

内部走的路径是：

```
自然语言 → _label_query() 翻成标签 → _find_fact(标签) → persona.key_facts 精确匹配
```

**设计取舍（如实说明）**：标签直查是"确定性命中"；**翻不出标签的口语问句**会退回通用检索，
而通用检索是**字面匹配**（`memvec` 是字符 n-gram 哈希，不是语义模型），命中率约 0.5。
所以要提升口语命中率，两条路：① 在 `key_facts.content` 里多写几种说法；
② 上层再接一个语义检索。本仓不假装它能做语义理解。

## 4. 危机识别与升级

```python
print(comp.detect_crisis("我胸口有点闷，喘不上气"))   # ['胸闷/心梗风险']
print(comp.detect_crisis("在卫生间滑倒了"))           # ['摔倒/外伤']
print(comp.detect_crisis("今天天气不错"))             # []
```

内置四类危机（`CRISIS_KEYWORDS`，模块级字典）：

| 类别 | 触发词（部分） |
|---|---|
| `胸闷/心梗风险` | 胸口闷 · 胸口疼 · 心慌 · 喘不上气 |
| `摔倒/外伤` | 摔了 · 摔倒了 · 地上 · 起不来 · 滑倒 |
| `意识异常` | 头晕 · 眼前发黑 · 站不稳 · 想吐 |
| `自伤/轻生` | 不想活 · 走了算了 · 没意思 |

要扩展（加方言 / 同义说法），直接改 `pasm_agents.companion.CRISIS_KEYWORDS`。

升级：

```python
info = comp.escalate("卫生间滑倒")
# 返回：
# {
#   "agent_id": "chenxiulan",
#   "persona_name": "陈秀兰",
#   "reason": "卫生间滑倒",
#   "suggested_action": "立即联系紧急联系人或拨打 120",
#   "emergency_contact": {"name": "女儿小敏", "phone": "13900000000"},
#   "snapshot": {...},        # 当时的 agent 快照，便于转述现场
#   "ts": 1789199924.2
# }
```

副作用：写入一条 `salience=5`、`category="危机"` 的紧急记忆，并 `feel(reason, -0.6)` 压低情绪。
**它不会真的打电话** —— 那是调用方的事。

## 5. 用药提醒

```python
for med in comp.due_medication(now_hour=8):     # 只返回该整点到点的药
    print(med["name"], med["dose"])

comp.due_medication()                           # 不传则按本机当前小时
```

逻辑是**纯时间比对**（`int(m["hour"]) == now_hour`），不涉及任何药理判断。

## 6. 交互模式

```bash
pasm-agents run companion --id=my_companion --persona-file=personas/chenxiulan.json
```

直接打字对话。可用命令：

| 命令 | 作用 |
|---|---|
| `facts` | 列出全部关键事实 |
| `mood` | 看当前情绪 |
| `act` | 执行一个动作 |
| `observe <文本>` | 手动写一条记忆 |
| `feedback <praise\|poke\|scold> [动作]` | 给反馈 |
| `snapshot` | 导出快照（JSON） |
| `quit` | 退出并 save |

## 7. 档位透明

| tier | 含义 | 何时启用 |
|---|---|---|
| `bionic` | 仿生：完整 PASM 核心 + emotion 模块（需 torch） | `pip install pasm-skills[torch]` |
| `core`    | 完整：PASM 核心（memory + learning，无 torch） | `PASM_PYTHON` 指向带核心的 Python |
| `light`   | 轻量：纯内置（重要度淘汰 + 字面检索 + softmax 权重） | 任何机器 |

## 8. 接入你自己的产品

```python
comp = ElderlyCompanion(agent_id="chenxiulan", persona=my_persona)   # 从你的配置构造

info = comp.escalate(user_text)                     # 你判断危机，你决定怎么通知
if "120" in info["suggested_action"] or comp.detect_crisis(user_text):
    my_notifier.send(info["emergency_contact"]["phone"], info["reason"])   # 由你实现

comp.save()                                        # 状态落 ~/.pasm-agents/<id>/
```

**智能体只负责"记得住、认得清、说得暖"，通知渠道由你接**（短信 / 电话 / 小程序 / 值班屏）。

## 9. 与验证层的关系

`pasm_skills/` 里的 `companion-elderly` 是**专门验证这类陪伴的智能体**：
跑 30 天，把「关键事实检索 100%」定为 FAIL 级，另外测危机命中率、回复是否同质化、
是否冒出工程术语、情绪能否从低谷恢复。它跑出的 4 个 WARN 是**真实能力短板**（口语检索、回复同质化），
已在 `docs/AGENTS.md` 如实列出，没有粉饰。

## 10. 相关技能

- `pasm-npc` —— 游戏 NPC 智能体
- `pasm-tutor` —— 学习陪伴智能体
- `pasm-longterm-verify` —— 验证层入口：回答"跑久了还是好的吗"
