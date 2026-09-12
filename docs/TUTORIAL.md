# PASM Skills 使用教程（TUTORIAL）

> 从"这是干什么的"到"我写出了一个能跑的智能体并打包发出去"，走一遍。
>
> - **不想读长文？** 直接跳到 [§2 六十秒验证](#2-六十秒验证) 和 [§4 路线 A](#4-路线-a写一个产品智能体)。
> - **只想用现成智能体？** 装 `pasm-agents`，不用读这份文档。
> - **想改基座本身？** 读 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

---

## 1. 先建立正确的心智模型

### 1.1 这个基座**不提供**智能体

第一件要记住的事：**`pasm-skills` 里一个智能体都没有**，这是刻意的。

```bash
$ pip install pasm-skills
$ python -m pasm_skills list
已发现的智能体 0 个：
  （无）基座不内置智能体。装一个智能体包即可：
      pip install pasm-agents       # 官方智能体集（NPC / 陪伴 / 教学 / 验证）
```

基座提供的是**写智能体的能力**，三样东西：

| 你拿到 | 用来干什么 |
|---|---|
| **SDK**（`pasm_skills.sdk.BaseAgent`） | 让"记忆 / 情绪 / 动作 / 反馈 / 持久化"开箱可用 |
| **框架**（`Agent` / `RepoContext` / `scenarios` / `checks`） | 写"给核心做体检"的验证智能体 |
| **打包库**（`pasm_skills.build`） | 把智能体打成平台能上传的技能包 |

### 1.2 两条互不依赖的扩展轴

这是最容易搞混的地方 —— **基座支持两类完全不同的智能体**：

| | 产品智能体 | 验证智能体 |
|---|---|---|
| 面向谁 | **使用者**（玩家 / 老人 / 学生） | **开发者**（你自己） |
| 基类 | `pasm_skills.sdk.BaseAgent` | `pasm_skills.agent.Agent` |
| 产出 | 对话、动作、情绪 | `[OK]` / `[WARN]` / `[FAIL]` 结论 |
| 靠什么支撑 | SDK | `context` + `scenarios` + `checks` |
| 典型例子 | 游戏 NPC、老人陪伴、学习陪伴 | 核心契约检查、长期行为体检 |

**它们不互相依赖。** 你可以只写产品智能体，完全不碰验证那一套；反之亦然。

### 1.3 档位：能力可降级，但绝不隐藏

任何智能体都跑在三个档位之一，`agent.tier` 会如实告诉你：

| tier | 依赖 | 得到什么 |
|---|---|---|
| `light` | 无 | 纯内置：重要度淘汰 + 字面检索 + 性格/反馈加权 |
| `core` | 能 `import pasm.cognitive`（**不需要 torch**） | 真 `memory_layers` 分层记忆 + `learning.LearningEngine` |
| `bionic` | 上面 + torch | 再加真情绪 / 人格模块 |

**三个档位下接口完全一致** —— 调用方不需要写分支。但你的智能体必须如实暴露 `tier`。

---

## 2. 六十秒验证

```bash
pip install pasm-skills

python -m pasm_skills selftest     # 15 项自检：SDK / 框架 / 发现机制
python -m pasm_skills list         # 三仓定位 + 已发现的智能体
python -m pasm_skills repos        # 只看仓库定位（JSON）
```

`selftest` 不需要 PASM 核心、不需要 torch、不需要任何外部智能体 —— 它是"基座自己没坏"的保证。

想马上看到"能写出什么"，跑自带的完整走查：

```bash
git clone https://gitee.com/arronzheng/pasm-skills
cd pasm-skills
python examples/build_your_agent.py     # 8 个环节：建→记忆→动作→对话→反馈→情绪→落盘→成长
python templates/agent_template.py      # 骨架自带的冒烟
```

---

## 3. 概念地图

写代码前先认这 6 个概念，后面会反复用到：

| 概念 | 一句话 | 在哪 |
|---|---|---|
| **persona** | 角色的画像（名字 / 性格 / 语气 / 业务数据） | 传给 `BaseAgent` 的 dict |
| **动作池**（`action_pool`） | 这个角色此刻能做什么 | 你实现 |
| **记忆**（`observe` / `recall`） | 经历 + **重要度**，容量满了按重要度淘汰 | SDK 提供 |
| **反馈**（`feedback`） | 夸/凶某个**具体动作**，让它以后多做/少做 | SDK 提供 |
| **档位**（`tier`） | 当前跑在哪一层，以及降级了没有 | SDK 探测 |
| **发现**（discovery） | 基座怎么找到你的智能体 | entry points / 环境变量 |

---

## 4. 路线 A：写一个产品智能体

### 4.1 最小可用版本（两个钩子）

```python
from pasm_skills.sdk import BaseAgent

class TeaHouseOwner(BaseAgent):
    def action_pool(self):                  # 钩子 1：能做什么
        return ["greet", "brew", "gossip", "rest"]

    def _render_reply(self, text, facts, mood):   # 钩子 2：怎么回
        tone = "蔫" if mood < -0.2 else "乐"
        facts_hint = f"（想起了「{facts[0]['title']}」）" if facts else ""
        return f"（{tone}）{self.persona.get('name')}：来了您呐{facts_hint}"

a = TeaHouseOwner(
    agent_id="owner",
    persona={"name": "王掌柜", "role": "巷口茶馆老板",
             "temper": 0.6, "energy": 0.3, "play": 0.4, "tone": "热情、话多"},
)
print(a.tier)                     # 'light' / 'core' / 'bionic'
print(a.act())                    # 'brew' / 'greet' / ...
print(a.chat("生意怎么样"))
a.save()
```

**就这两个钩子。** 其余全部由 SDK 承担。

### 4.2 加记忆：重要度决定谁活下来

```python
a.observe("今天下雨，人少")                                    # 默认 salience=1，最先被淘汰
a.observe("小姑娘每周三都来买桂花糕", brief="不要糖",
          tags=["熟客", "桂花糕"], salience=3, category="熟客")
a.observe("上周替隔壁摊主挡了一次醉汉", tags=["大事"], salience=5, category="里程碑")

print(a.recall("桂花糕", k=3))
# -> [{'title': '小姑娘每周三都来买桂花糕', 'brief': '不要糖', 'tags': [...], 'sal': 3}, ...]
```

- 容量上限 **200 条**，触顶时按 `(salience, 新旧)` 淘汰 —— **重要度优先，同重要度留新的**。
- `salience` 语义：`1` 日常 / `3` 值得记 / `5` 关键（里程碑、安全事实）。
- **检索是字面匹配**（`light` 与 `core` 都一样），不是语义匹配。想让某句话被检索到，
  标签里就带上人们会说的词。

### 4.3 加行为塑形：反馈一定要指定动作

```python
a.feedback("praise", action="brew")    # +0.3
a.feedback("hug",    action="brew")    # +0.15
a.feedback("poke",   action="rest")    # -0.05
a.feedback("scold",  action="rest")    # -0.3
```

实测效果（`seed=0`，400 次 `act()` 采样，60×`praise(brew)` + 60×`scold(rest)`）：

| 档位 | `brew`（被夸） | `rest`（被凶） |
|---|---|---|
| `light` | 0.26 → **1.00** | 0.26 → **0.00** |
| `core` | 0.27 → **0.80** | 0.26 → **0.03** |

> 这组数字可复现：`BaseAgent(..., seed=0)`。两档都生效，只是 `light` 的权重更"陡"
> （纯加权采样），`core` 走真 `LearningEngine`，带 ε-贪心探索，所以不会压到 0/1 两端。

⚠️ **不传 `action` 会怎样**：反馈会作用在"当前最偏好的动作"上 —— 偏好越高越加码，
长期下来行为**极端化**。所以 `action` 基本等于必填。

**两个档位走同一套语义**：`得分 = 性格基线 + 学习权重`，然后采样。

### 4.4 性格怎么影响动作

`persona` 里三个 0~1 的量和动作名里的**关键词**挂钩：

| 动作名含 | 受哪个特质影响 | 含义 |
|---|---|---|
| `wave` `talk` `share` `teach` `give` | `temper` | 主动搭话 vs 沉默旁观 |
| `hop` `dance` `spin` `ball` `run` | `energy` | 爱动 vs 爱歇 |
| `peek` `play` `joke` `boast` | `play` | 俏皮 vs 正经 |

动作名不带关键词 = 均匀偏好。想让自定义名字被识别，**覆盖 `_fallback_weights()`**
（注意：**没有** `ACT_BIAS` 之类的配置项）：

```python
def _fallback_weights(self, pool):
    base = super()._fallback_weights(pool)
    boost = {"brew": 2.0, "rest": 0.5}
    return [w * boost.get(a, 1.0) for a, w in zip(pool, base)]
```

### 4.5 加情绪

```python
print(a.mood)                              # float ∈ [-1, 1]（**属性，不加括号**）
a.feel("茶馆被泼了脏水", valence=-0.6)      # 注入一次情绪事件
```

`mood` 会被传进 `_render_reply(text, facts, mood)`，所以"同一句话在高兴和生气时说出来的不一样"
是自然发生的，不用你写 if-else。

### 4.6 加结构化状态：用 `state.notes`

需要按知识点记分、记用药表、记任务进度时，**放 `state.notes`**（随 state 一起落盘，不用另开文件）：

```python
def report(self, topic, score):
    ks = self.state.notes.setdefault("knowledge_state", {})
    ks[topic] = round(ks.get(topic, 0.0) * 0.7 + score * 0.3, 3)   # EMA 平滑
    return {"topic": topic, "new_mastery": ks[topic]}

def snapshot(self):        # ★ 给外部一个稳定的机读出口
    ks = self.state.notes.get("knowledge_state") or {}
    return {"mastery": ks,
            "weakest": min(ks, key=ks.get) if ks else None,
            "tier": self.tier}
```

**原则**：外部要读的，给一个 `snapshot()`；`state.notes` 是内部状态，别让调用方伸手进去。

### 4.7 首次启动的初始记忆

```python
def bootstrap_event(self):
    """仅在 total_interactions == 0 时被调用；每项会当作 observe(**item)。"""
    return [{"title": "我在巷口开了家茶馆", "tags": ["茶馆"], "salience": 3}]
```

### 4.8 完整方法速查

| 方法 | 签名 | 说明 |
|---|---|---|
| `__init__` | `(agent_id, persona, persist_dir=None, *, use_core=True, seed=None)` | `use_core=False` 强制轻量档（写测试用） |
| `observe` | `(title, brief="", tags=None, *, salience=1, category="日常")` | 写记忆 |
| `recall` | `(query, k=5) -> List[Dict]` | 检索记忆 |
| `act` | `() -> str` | 选一个动作 |
| `chat` | `(text) -> str` | 走 `_render_reply`，并把这次对话写进记忆 |
| `feedback` | `(kind, action=None) -> Dict[str, float]` | `kind` ∈ `praise`/`hug`/`poke`/`scold`/`ignore` |
| `feel` | `(event, valence) -> None` | 注入情绪事件 |
| `mood` | **属性** `-> float` | 当前情绪 |
| `tier` | **属性** `-> str` | 当前档位 |
| `save` | `() -> Path` | 落盘 |
| `summary` | `() -> Dict` | 可读快照 |
| `action_pool` / `_render_reply` / `bootstrap_event` | 见上 | 你来实现 |

---

## 5. 路线 B：写一个验证智能体

验证智能体回答的是"**这个引擎跑久了还是好的吗**"，产出结构化结论。它与产品智能体**完全无关**。

### 5.1 结构型验证（静态探测）

```python
# my_agents/api_guard.py
from pasm_skills.agent import Agent, register

@register
class ApiGuard(Agent):
    """守护核心公开 API 不许擅自增删。"""
    name = "api-guard"
    goal = "核心导出的公开 API 不得擅自增删"
    needs = ("core",)          # 声明依赖哪些仓；缺了会自动 SKIP

    def run(self):
        code = (
            "import json\n"
            "from pasm import engine_api as ea\n"
            "print(SENTINEL + json.dumps(sorted(dir(ea))))\n"
        )
        data = self.ctx.probe("core", code).get("json")
        if data is None:
            self.fail("探测失败", "core 仓无法导入 engine_api")
        else:
            self.ok("API 快照可用", "%d 个公开名" % len(data))
        return None
```

跑起来（**不用打包、不用安装**）：

```bash
PASM_SKILLS_PATH=./my_agents python -m pasm_skills run api-guard
```

`self.ctx.probe(仓键, 代码)` 在**独立子进程**里、以该仓为 cwd 执行代码。
三个仓存在同名模块，同进程 import 会互相顶掉 —— 这是必须开子进程的原因。

### 5.2 行为型验证（跑场景）

```python
from pasm_skills.agent import Agent, register
from pasm_skills import scenarios as S

SCENARIO = r'''
import random
from pasm.cognitive.learning import LearningEngine
eng = LearningEngine(data_path=None)
for topic in ("分数加减", "面积计算"):
    for _ in range(20):
        eng.learn(action=topic, delta=0.3)
# 停练 25 天（这里用 25 次"没有强化"的空转近似）
...
emit({"decay": span(scores), "retained": rate(hits, len(probes))})
'''

SPEC = [
    {"key": "retained", "title": "停练后仍能召回", "lo": 0.8, "fmt": "{:.3f}"},
    {"key": "decay",    "title": "遗忘曲线存在",   "lo": 0.05, "bad": "fail",
     "note": "安全关键项：不衰减意味着学情会失真"},
]

@register
class MyDecayVerifier(Agent):
    name = "my-decay"
    goal = "验证学习层有没有时间衰减"
    needs = ("core",)

    def run(self):
        python, torch_ok = S.choose_python(self.ctx, prefer_torch=True)
        tier = "仿生层 torch" if torch_ok else "轻量档"
        res = S.run_scenario(self.ctx, SCENARIO, repo="core", python=python)
        m = S.metrics_of(res)
        if m is None:
            self.skip("场景未产出指标", S.failure_detail(res))
            return None
        S.judge(self, m, SPEC, tier=tier)
        self.extra = {"metrics": m, "python": S.python_label(python)}
        return None
```

**场景底座管住最麻烦的三件事**：

| 工具 | 作用 |
|---|---|
| `S.choose_python(ctx, prefer_torch=True)` → `(python, torch_ok)` | 挑解释器（优先带 torch），**档位一路传到结论里** |
| `S.run_scenario(ctx, body, repo=...)` | 隔离子进程跑场景，自动带上 `PRELUDE` |
| `S.judge(agent, metrics, spec, tier=...)` | 阈值表 → `OK/WARN/FAIL/SKIP` |

`PRELUDE` 已注入这些裸函数，场景代码里直接用：

```
emit / entropy / norm_entropy / tv_distance / topk_by / hits_in / ghost_max /
bounded / max_jump / span / mean / slope / rate / temp_layers / cleanup / TORCH_OK
```

### 5.3 阈值表 `spec` 怎么写

```python
{"key": "指标名", "title": "结论标题",
 "lo": 下限, "hi": 上限,          # 单边可省
 "bad": "fail",                  # 越界记 FAIL（默认记 WARN）
 "fmt": "{:.3f}",                # 展示格式
 "note": "给读者的解释"}
```

- 越界**默认记 `WARN`** —— 多数"越界"其实是产品能力短板，不是缺陷。
- **安全关键项**才用 `bad="fail"`（例：老人用药事实检索不出来）。
- 指标缺失（场景没产出）自动记 `SKIP` 并说明原因 —— **`SKIP` 不是"没问题"**。

### 5.4 三条不可违反的红线

1. **场景必须驱动真实核心组件。** 拿不到就 `SKIP`，**绝不允许手搓替身** —— 假绿比没查更危险。
2. **降级必须可见。** 用哪一档跑，就写进每一条结论。
3. **只读。** 验证过程不修改被检查的仓，只写自己的 `baselines/`。

---

## 6. CLI 全参考

```bash
pasm-skills <子命令>          # 装了包之后
python -m pasm_skills <子命令>  # 不用装也能跑（在仓根）
```

| 子命令 | 作用 |
|---|---|
| `selftest` | 框架自检（15 项，零依赖） |
| `list` | 三仓定位 + 已发现的智能体 |
| `agents` | **排障用**：报告每个智能体是从哪加载进来的 |
| `repos` | 只打印仓库定位（JSON） |
| `run <名...>` | 跑指定智能体（可多个） |

`run` 的参数：

| 参数 | 说明 |
|---|---|
| `--all` | 跑全部已发现的智能体 |
| `--json` | 输出 JSON |
| `--out <文件>` | 把 JSON 写到文件（父目录会自动建） |
| `--quiet` | 只显示非 OK 结论 |
| `--baseline <名>` | 指定基线名（默认 `core`） |
| `--update` | 刷新基线（**只在确认当前状态正确时用**） |

**退出码**：`0` 全部通过 · `1` 有 `FAIL` · `2` 用法/定位错误 —— 可直接接 CI。

```bash
python -m pasm_skills run --all --out reports/$(date +%F).json || echo "有失败项"
```

---

## 7. 环境变量全参考

### 7.1 让基座找到你的智能体（discovery）

按优先级从高到低：

| 变量 | 用法 | 适合 |
|---|---|---|
| `PASM_SKILLS_PATH` | 指向一个 `.py` 或目录，里面每个 `.py` 都会被加载 | **本地开发最快** |
| `PASM_SKILLS_AGENT_MODULES` | 逗号分隔的模块名 | 测试环境显式钉死 |
| （entry points） | 安装包里声明 `[project.entry-points."pasm_skills.agents"]` | **正式发布** |

```bash
# 本地跑自己刚写的
PASM_SKILLS_PATH=./my_agents python -m pasm_skills list

# 显式钉死模块
PASM_SKILLS_AGENT_MODULES=pasm_agents.verifiers python -m pasm_skills list
```

**三道都失败也不报错** —— 基座照样能 `selftest`，只是智能体数为 0。

### 7.2 被检查的仓库定位

| 变量 | 对应仓 |
|---|---|
| `PASM_CORE` | 核心包（`pasm/`） |
| `PASM_STUDIO` | 桌面端仓（`desktop/`） |
| `PASM_LITE` | 教学版 |
| `PASM_SKILLS_ROOTS` | 兜底：在这些目录下按名找 |

### 7.3 解释器选择（决定跑哪一档）

按优先级：

```
PASM_TORCH_PYTHON → PASM_PYTHON → ~/.pasm-skills/local.json
  → sys.executable → 仓库内 .venv/venv → py → python3 → python
```

```bash
export PASM_PYTHON=/path/to/python          # 最高优先，显式钉死
export PASM_TORCH_PYTHON=/path/to/python    # 指定"带 torch"的解释器
```

或写本机配置（**在仓库外，不会入库**）：

```json
// ~/.pasm-skills/local.json
{ "python": ["%%HOME%%/venv/bin/python"] }
```

> ⚠️ 建议指向**自带 site-packages 的 venv**，别用系统 Python：
> 若环境改写了 `APPDATA`，Python 的 user site-packages 会指向别处，
> 装在 user site 里的 torch 就会"时有时无"（表现为结论突然全变成轻量档）。

---

## 8. 打包与发布技能包

### 8.1 在你自己仓里加两个文件

```
your-repo/
├── pyproject.toml              # version 是唯一来源
├── skill/
│   └── SKILL.my-agent.body.md  # 正文（复制 templates/SKILL.template.body.md）
└── tools/
    └── build_skill.py          # 声明技能清单
```

```python
# tools/build_skill.py
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pasm_skills.build import ProjectMeta, SkillSpec, run_cli

META = ProjectMeta(author="you", homepage="https://github.com/you/your-repo")
SKILLS = [SkillSpec(
    name="my-agent",
    body_file="SKILL.my-agent.body.md",
    display_name_zh="我的智能体",
    display_name_en="My agent",
    desc_zh="……（中文描述必须含触发词）",
    desc_en="……",
    plain_desc="……（英文）",
    plain_category="agents",
    plain_tags=["pasm", "my-agent"],
)]

if __name__ == "__main__":
    raise SystemExit(run_cli(SKILLS, META, root=ROOT))
```

### 8.2 跑

```bash
python tools/build_skill.py --zip --clean
```

产物（两种**归档形态**，按结构命名，不按平台名）：

```
your-repo-dist/
├── zip-root/my-agent/SKILL.md     # ZIP 直接打这个目录（SKILL.md 落在根）
├── slug-dir/my-agent/SKILL.md     # 上传"这个文件夹"
└── my-agent-<version>.zip         # 内含且仅含 SKILL.md
```

⚠️ `zip-root` 形态**必须**把 `SKILL.md` 放在 ZIP 根目录 —— 包成 `skills/<name>/SKILL.md`
会被平台拒收（报「压缩包缺少 SKILL.md 文件」）。脚本内置结构自检，错了直接 `[FAIL]`。

细节（frontmatter 逐字段、许可证差异、中文不折行的原因）见 [`SKILL-FORMAT.md`](SKILL-FORMAT.md)。

---

## 9. 排查手册

| 症状 | 原因 | 处理 |
|---|---|---|
| `list` 显示 0 个智能体 | 基座不内置，正常 | 装 `pasm-agents`，或设 `PASM_SKILLS_PATH` |
| `[WARN] 智能体模块导入失败` | 模块名写错 / 路径没加 | `python -m pasm_skills agents` 看加载来源 |
| `[SKIP] 仓库 core 未找到` | 路径没定到 | 设 `PASM_CORE` 或 `PASM_SKILLS_ROOTS` |
| 结论全是轻量档 | 没找到带 torch 的解释器 | 设 `PASM_TORCH_PYTHON`，或用本机配置文件 |
| `[WARN] 档位不同·不可比` | 基线与本次解释器不同 | 固定解释器后 `regression --update` 重建基线 |
| `[FAIL] ... 文件被移除` | 真的删了文件 | 看 detail 里的文件名，回对应仓确认 |
| `[SKIP] 场景未产出该指标` | 场景代码抛异常 | 加 `--json` 看 `extra`，或手跑那段场景代码 |
| `act()` 报 `NotImplementedError` | 没实现 `action_pool` | 见 §4.1 |
| `chat()` 报 `NotImplementedError` | 没实现 `_render_reply` | 见 §4.1 |
| `a.mood()` 报 `'float' object is not callable` | `mood` 是**属性** | 写 `a.mood` |
| 反馈后行为没变化 | `feedback` 没传 `action` | 传上（见 §4.3） |
| 关键记忆被挤掉了 | 没用 `salience=5` | 见 §4.2 |

---

## 10. 进阶

### 10.1 接进 CI

```yaml
- run: pip install pasm-skills pasm-agents
- run: python -m pasm_skills run --all --out report.json
```

退出码 `1` 就是有 `FAIL`，不用解析输出。

### 10.2 定时跑

- **Windows 任务计划**：每天跑 `run --all --out reports\YYYY-MM-DD.json`
- **本机助手定时任务**：说"每天早上 9 点跑一次全量验证并归档"
- **GitHub Actions**：公开仓免费（见本仓 `.github/workflows/selfcheck.yml`）

**不需要服务器** —— 详见 [`SERVER-NEEDS.md`](SERVER-NEEDS.md)。

### 10.3 判断"有没有退化"

```bash
python -m pasm_skills run regression              # 与基线比对
python -m pasm_skills run regression --update     # 确认现状正确后重建基线
```

它比对：认知层文件指纹 / 引擎清单 / 契约版本。基线与本次**档位不同**时，
清单类结论会降级为 `[WARN] 档位不同·不可比` —— 那不是退化，是换了把尺子。

### 10.4 站在产品智能体上再包一层

产品智能体是普通 Python 对象，可以塞进任何东西：

```python
# FastAPI 里
@app.post("/chat")
def chat(agent_id: str, text: str):
    a = MyAgent(agent_id=agent_id, persona=load_persona(agent_id))   # 会自动恢复状态
    return {"reply": a.chat(text), "tier": a.tier}

# 游戏循环里
if dungeon_tick():
    npc.observe("玩家进入了地牢", salience=3, tags=["玩家"])
    play_animation(npc.act())
```

---

## 11. 文件速查

```
pasm-skills/
├── pasm_skills/
│   ├── sdk/base.py         ★ BaseAgent（写产品智能体只看这个）
│   ├── agent.py            Agent 基类 / AgentResult / Finding / 注册表
│   ├── discovery.py        智能体发现
│   ├── context.py          RepoContext 隔离探测
│   ├── scenarios.py        场景仿真底座
│   ├── checks.py           核心契约检查工具箱
│   ├── build.py            ★ 打包库
│   └── cli.py              CLI
├── templates/              ★ 复制就能改
├── examples/               可跑走查
├── docs/
│   ├── TUTORIAL.md         ← 你在这里
│   ├── BUILD-AGENT.md      从零到发版（更偏教程）
│   ├── SKILL-FORMAT.md     技能包格式
│   ├── ARCHITECTURE.md     框架分层与设计取舍
│   └── SERVER-NEEDS.md     服务器需求评估（结论：不需要）
└── tools/build_skill.py    本仓的打包声明
```

**下一步**：
- 想抄现成的 → 读 [pasm-agents](https://github.com/arronJack/pasm-agents) 的源码（3 产品 + 7 验证）
- 想看怎么设计一个智能体 → [`BUILD-AGENT.md`](BUILD-AGENT.md)
- 想改基座本身 → [`ARCHITECTURE.md`](ARCHITECTURE.md)
