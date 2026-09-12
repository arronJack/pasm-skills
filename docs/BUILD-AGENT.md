# 从零写一个 PASM 智能体（BUILD-AGENT）

> 目标：**30 分钟内**做出一个能跑、能记忆、有情绪、能被反馈塑形、能落盘的智能体，
> 并打成平台可上传的技能包。
>
> 前置：`pip install pasm-skills`（零依赖，不需要 PASM 核心、不需要 torch、不需要 API key）。

---

## 一、先分清两层

| | 产品智能体 | 验证智能体 |
|---|---|---|
| 基类 | `pasm_skills.sdk.BaseAgent` | `pasm_skills.agent.Agent` |
| 干什么 | 陪人 / 扮演 / 教学 —— **面向使用者** | 给核心做体检 —— **面向开发者** |
| 产出 | 对话、动作、情绪、记忆 | `[OK]/[WARN]/[FAIL]` 结论 |
| 例子 | `pasm-agents` 仓的 NPC / 陪伴 / 教学 | `pasm-agents` 仓的 `core-verifier` 等 |

**本文只讲产品智能体。** 验证智能体见 SKILL 文档 §10。

---

## 二、最小智能体

```python
from pasm_skills.sdk import BaseAgent

class TeaHouseOwner(BaseAgent):
    def action_pool(self):                 # 必填 1：能做什么
        return ["greet", "brew", "gossip", "rest"]

    def _render_reply(self, text, facts, mood):   # 必填 2：怎么回
        return f"（{'蔫' if mood < -0.2 else '乐'}）{self.persona.get('name')}：来了您呐"

a = TeaHouseOwner(agent_id="owner", persona={"name": "王掌柜", "temper": 0.6})
a.observe("客人夸今年的龙井好", salience=3)
print(a.act(), a.chat("生意怎么样"), a.mood)
a.save()
```

就这两个钩子。其余（记忆淘汰、情绪衰减、动作采样、落盘）基座都做好了。

---

## 三、`BaseAgent` 完整参考

### 构造

```python
BaseAgent(agent_id, persona, persist_dir=None, *, use_core=True, seed=None)
```

| 参数 | 说明 |
|---|---|
| `agent_id` | 全局唯一。同一个 id 再次实例化会**恢复上次状态** |
| `persona` | 角色画像 dict。约定键：`name` / `role` / `temper` / `energy` / `play` / `tone`，其他键随你用 |
| `persist_dir` | 落盘目录，缺省 `~/.pasm-agents/<agent_id>` |
| `use_core` | 是否尝试接 PASM 真核心。`False` 强制轻量档（写测试时有用） |
| `seed` | 固定随机种子，便于复现 |

### 必填钩子

| 钩子 | 签名 | 说明 |
|---|---|---|
| `action_pool()` | `-> List[str]` | 当前能做的动作。动作名里的关键词决定它受哪个性格特质影响（见 §四） |
| `_render_reply(text, facts, mood)` | `-> str` | `facts` 是检索到的记忆（list，可能空），`mood` ∈ [-1,1] |

### 可选钩子

```python
def bootstrap_event(self) -> List[Dict[str, Any]]:
    """首次启动时写入的初始记忆。每项会被当作 observe(**item)，默认返回 []。"""
    return [{"title": "我在巷口开了家茶馆", "tags": ["茶馆"], "salience": 3}]
```

### 公开方法

| 方法 | 签名 | 说明 |
|---|---|---|
| `observe` | `(title, brief="", tags=None, *, salience=1, category="日常")` | 写一条经历 |
| `recall` | `(query, k=5) -> List[Dict]` | 检索记忆 |
| `act` | `() -> str` | 选一个动作（性格基线 + 反馈权重） |
| `chat` | `(text) -> str` | 走 `_render_reply`；顺带把这次对话写进记忆 |
| `feedback` | `(kind, action=None) -> Dict[str, float]` | `kind` ∈ `praise`/`hug`/`poke`/`scold`/`ignore` |
| `feel` | `(event, valence) -> None` | 注入一次情绪事件（valence ∈ [-1,1]） |
| `mood` | **属性**（不是方法） | 当前情绪 float |
| `save` | `() -> Path` | 落盘 |
| `summary` | `() -> Dict` | 可读快照（含 `tier`） |
| `tier` | **属性** | `light` / `core` / `bionic` |

> ⚠️ `mood` 是 `@property` —— 写 `a.mood`，**不要写 `a.mood()`**。

---

## 四、动作名与性格特质

默认实现按**动作名里的关键词**把性格特质映射成偏好：

| 关键词 | 受哪个特质影响 |
|---|---|
| `wave` `talk` `share` `teach` `give` | `temper`（主动 vs 沉默） |
| `hop` `dance` `spin` `ball` `run` | `energy`（爱动 vs 爱歇） |
| `peek` `play` `joke` `boast` | `play`（俏皮 vs 正经） |

动作名不带关键词也行 —— 那就是均匀偏好。**没有 `ACT_BIAS` 之类的配置项**；
想让自定义动作名被识别，直接覆盖：

```python
def _fallback_weights(self, pool):
    base = super()._fallback_weights(pool)
    boost = {"brew": 2.0, "rest": 0.5}
    return [w * boost.get(a, 1.0) for a, w in zip(pool, base)]
```

---

## 五、记忆：重要度决定谁会活下来

```python
a.observe("今天下雨，人少")                                  # salience=1，最先被淘汰
a.observe("小姑娘每周三都来买烤面筋", tags=["熟客"], salience=3)
a.observe("上周帮隔壁摊主挡了一次醉汉", tags=["大事"], salience=5)   # 不会被挤掉
```

容量上限 200 条，触顶时按 `(salience, -索引)` 淘汰 —— **重要度优先，其次留新的**。

**检索是字面匹配**（轻量档与核心档都是），不是语义匹配。想让某句话被检索到，
标签里就带上人们会说的词。要语义检索，得自己在 `recall` 外面接一层。

---

## 六、反馈：一定要指定动作

```python
a.feedback("praise", action="brew")    # +0.3
a.feedback("scold",  action="rest")    # -0.3
```

不传 `action` 时，反馈会作用在"当前最偏好的动作"上 —— 偏好越高越加码，
长期下来行为会**极端化**（实测可复现）。所以 `action` 基本等于必填。

---

## 七、扩展结构化状态：用 `state.notes`

需要按知识点记分、记用药表、记任务进度时，**放在 `state.notes` 里** ——
它会随 `agent_state.json` 一起落盘，不需要自己开文件：

```python
def report(self, topic, score):
    ks = self.state.notes.setdefault("knowledge_state", {})
    prev = ks.get(topic, 0.0)
    ks[topic] = round(prev * 0.7 + score * 0.3, 3)     # EMA 平滑
    return {"topic": topic, "new_mastery": ks[topic]}

def snapshot(self):        # 给外部一个稳定的机读出口，别让调用方读 notes
    ks = self.state.notes.get("knowledge_state") or {}
    return {"mastery": ks, "weakest": min(ks, key=ks.get) if ks else None,
            "tier": self.tier}
```

**原则**：外部要读的，给一个 `snapshot()` 出口；`state.notes` 是内部状态。

---

## 八、档位：三个层次，一个接口

| tier | 依赖 | 得到什么 |
|---|---|---|
| `light` | 无 | 内置实现：重要度淘汰 + 字面检索 + 性格/反馈加权 |
| `core` | 能 `import pasm.cognitive` | 真 `memory_layers`（分层记忆）+ `learning.LearningEngine`（性格设计 + ε-贪心） |
| `bionic` | 上面 + torch + `pasm.modules.emotion` | 再加真情绪/人格模块 |

**三个档位下 `BaseAgent` 的接口完全一致**，所以调用方不需要写分支。
但你要**如实告诉用户现在在哪一档**：

```python
print(a.tier)          # 别把它藏起来
```

想让本机跑高档位 → 见 README「本机配置」。
`pasm-agents` 仓的验证智能体会把档位写进**每一条**结论里，就是这个道理。

---

## 九、落盘

```python
a.save()
# ~/.pasm-agents/<agent_id>/
# ├── agent_state.json      persona / 交互数 / 反馈历史 / mood / notes
# ├── episodes.json         light 档记忆（core/bionic 档走 pasm.cognitive.memory_layers）
# └── action_weights.json   动作权重
```

同 `agent_id` 再次实例化即恢复。**`persona` 以本次传入的为准**（允许改人设而不丢记忆）。

---

## 十、打成技能包

1. 把正文放到 `skill/SKILL.<name>.body.md`（复制 `templates/SKILL.template.body.md`）；
2. 写 `tools/build_skill.py`（照抄示例，声明 `SKILLS` 列表）；
3. 跑：

```bash
python tools/build_skill.py --zip --clean
```

产物两种形态（详解见 [SKILL-FORMAT.md](SKILL-FORMAT.md)）：

```
<repo>-dist/
├── zip-root/<name>/SKILL.md       # ZIP 直接打这个目录（SKILL.md 落在根）
├── slug-dir/<name>/SKILL.md       # 上传"这个文件夹"
└── <name>-<version>.zip           # 内含且仅含根目录 SKILL.md
```

版本号取自 `pyproject.toml`，两种形态永远一致；结构不对会直接 `[FAIL]` 退出。

---

## 十一、把智能体交给基座发现

写完之后，让 `pasm-skills` 能找到它。**三种方式，按优先级**：

```bash
# 1) 本地开发：指向文件或目录（最快）
PASM_SKILLS_PATH=/path/to/my_verifier.py python -m pasm_skills run my-verifier

# 2) 显式钉死模块名
PASM_SKILLS_AGENT_MODULES=my_pkg.agents python -m pasm_skills list

# 3) 正式发布：装成包，声明 entry point（推荐）
```

```toml
# pyproject.toml
[project.entry-points."pasm_skills.agents"]
my-agents = "my_pkg.agents"
```

装好后 `python -m pasm_skills list` 就能看到；排障用 `python -m pasm_skills agents`
（它会打印每个智能体是从哪加载进来的）。

---

## 十二、检查清单

发布前逐条过：

- [ ] `_render_reply` 与 `action_pool` 都实现了，且**示例代码实跑过**
- [ ] `feedback()` 的调用都传了 `action=`
- [ ] 关键记忆用了 `salience=5`
- [ ] 额外状态放 `state.notes`，并有 `snapshot()` 机读出口
- [ ] `tier` 没有被隐藏；差档位时的能力短板写进文档「已知短板」
- [ ] 文档里的每个 API 都真实存在（**别凭印象写签名**）
- [ ] `python tools/build_skill.py --zip` 通过（结构自检会拦下错的 ZIP）
- [ ] `python -m pasm_skills selftest` 通过

---

## 十三、下一步

- 读 `pasm-agents` 仓的源码 —— **三个官方智能体 + 七个验证智能体是最好的教程**；
- 协议与格式：`docs/SKILL-FORMAT.md`
- 框架分层与设计取舍：`docs/ARCHITECTURE.md`
