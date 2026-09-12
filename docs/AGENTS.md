# 智能体总览 · AGENTS

> 本仓的智能体不是"能聊天的角色"，而是**可反复运行、产出结构化结论的长期验证器**。
> 零依赖、不常驻、不需要服务器 —— 长期验证要的是可重复、可比较、可归档。

## 一、为什么"结构体检"不够

`core-verifier` 查的是**结构**：文件在不在、契约满不满足、两仓一不一致。
这些能挡住"改坏了"，但挡不住"跑久了才坏的"：

| 失效类型 | 结构体检能发现吗 | 只有长期场景能发现 |
|---|---|---|
| 记忆库触顶后把最重要的经历先丢掉 | ✗ | ✓ |
| 情绪在几百步后漂到边界钉死 | ✗ | ✓ |
| 行为分布慢慢塌缩成"只做一件事" | ✗ | ✓ |
| 老人用口语问，系统存的是书面词，问不出来 | ✗ | ✓ |
| 学习层没有遗忘机制，三个月前的学情和昨天一样 | ✗ | ✓ |
| 存档读回来少了几个字段，第二天才发现 | 部分 | ✓ |

所以本仓的智能体分三层：

```
守门层（原有）    core-verifier · parity-guard · regression        ← 结构与一致性
领域层（本次）    npc-lifelong · companion-elderly
                  study-tutor · soak-longrun                       ← 行为与长期退化
```

## 二、选型分析：为什么是这四个

判断一个场景值不值得做成智能体，看四条：

1. **能否驱动真实核心组件**（不能自己写替身，否则验的是假货）；
2. **是否有"长期"维度**（短测看不出来的东西才值得单独立项）；
3. **失效后果是否严重**（忘了老人过敏史 = 事故，值得用 FAIL 级断言守住）；
4. **是否对准产品方向**（能顺手回答"引擎够不够支撑上层"）。

按这四条过一遍 PASM 的能力面：

| 候选场景 | 驱动核心 | 长期维度 | 后果 | 结论 |
|---|---|---|---|---|
| **游戏 NPC 长期生命** | 分层记忆 / 情绪 / 人格 / 行为偏好学习 | 强（90 天） | 中 | ✅ **做** |
| **老人陪伴** | 分层记忆 / 检索 / 情绪 / 旁白 | 强（30 天） | **高**（健康与用药） | ✅ **做** |
| **学习陪伴** | 行为偏好学习 / 错题检索 / 学情结构 | 强（30 天） | 中高 | ✅ **做**（另：直连霖云智学画像 v2） |
| **长效耐久（soak）** | 轻量认知体 / 行为引擎 / 存档 | **极强**（6000+ 步） | 高（线上才炸） | ✅ **做**（正交维度） |
| 客服 / 销售话术 | 弱（主要靠 LLM） | 弱 | 低 | ❌ 不做，引擎层没有对应能力 |
| 通用闲聊质量 | — | — | — | ❌ 不做，属于模型评测，不属于引擎验证 |
| 安全底线守护 | 尚未落盘 | 中 | **极高** | ⏸ 先做**结构探查**（已并入 core-verifier），等核心有安全层再做行为级 |
| 人格一致性专项 | 人格模块 | 强 | 中 | ⏸ 与 NPC 重叠，先并入 npc-lifelong 的 `pers_drift` |
| 联网自学 / 知识获取 | knowledge 层 | 强 | 中 | ⏸ 需要真实网络与 LLM 调用，与"零依赖"冲突，另立仓更合适 |

> 一句话：**选那些"跑得越久越容易坏、坏了后果越严重"的场景**。

## 三、四个领域智能体

### 1. `npc-lifelong` —— 游戏 NPC 的长期生命

**场景**：小镇 NPC 活 90 天 × 每天 3 件事 = 270 段经历，含一次"玩家救了我"级别的里程碑、
被野狗追的坏事、以及大量平淡日常。第 1 天埋一条重要度 5 的记忆，看它 90 天后还在不在。

**驱动**：`cognitive.memory_layers`（分层记忆）· `cognitive.memvec`（向量召回）·
`cognitive.memrouter`（记忆路由）· `cognitive.learning`（行为偏好）·
`modules.emotion` + `Personality`（有 torch）／`light.PASMAgent`（无 torch）

**断言（19 条）**：容量不失控 · 遗忘区分重要度 · 里程碑记忆存活 · 重要关系可召回 ·
跨 90 天长程召回 · 无中生有防护 · 路由准确率 · 记忆可还原成自然语言 ·
情绪有界 / 无瞬移 / 有起伏 · 行为熵不塌缩 / 长尾仍出现 / 行为偏好真的学进去 ·
善待与苛待导致行为分布不同 · 反馈可指定动作 · 人格不漂走

**首跑抓到 3 个真问题**（见第五节）→ 修核心 → 复跑全绿。

### 2. `companion-elderly` —— 老人陪伴

**场景**：陈奶奶 78 岁，30 天。每天重复念叨用药/过敏/家人/住址，
中间经历一段"想儿子 + 身体不适"的低落期，随后视频通话与孙辈照片介入；
第 9 / 21 天各发生一次健康事件（半夜胸口闷、卫生间差点滑倒）。

**刻意分开测两件事**，因为失效方式完全不同：

- **存没存住**（`lookup_rate`）—— 存不住是事故，判 **FAIL**，必须 100%；
- **问得出来吗**（`ask_rate` / `layer_rate`）—— 检索不到是能力短板，判 **WARN**。

**断言（17 条）**：关键信息留存 · 纯口语问句可检索 · 生产检索路径同样可检索 ·
重复提问答复一致 · 跨天连续 · 健康事件长期可召回 · 无中生有防护 ·
情绪安抚有效 / 不穿底 / 有界 · 单段字数对老人友好 · 回忆文本无术语 · 旁白可用

### 3. `study-tutor` —— 学习陪伴

**场景**：小雅 30 天 × 每天 4 题，6 个知识点，其中"图形对称"只在前 5 天练过、
之后彻底停练 —— 专门用来暴露"有没有遗忘机制"。

**驱动**：`cognitive.learning`（知识点强化量）· `cognitive.memory_layers`（错题与讲法）·
`cognitive.memvec`（相似错题检索）· `modules.emotion`

**断言（14 条）**：强化可累加 / 有区分度 · **停练会衰减（遗忘曲线）** · 相似错题可检索 ·
学情可解释 · 讲法经验可复用 · 状态含契约字段且可 JSON 序列化 ·
可导出「知识点 → 强化量」 · 鼓励:纠正配比合理 · 情绪有界有起伏 · 未练知识点不凭空出现

> 这个智能体同时是**霖云智学画像 v2 的前置体检**：`profile` 与 `state` 两个输出
> 就是画像层能直接消费的结构，缺什么一眼能看出来。

### 4. `soak-longrun` —— 长效耐久

**场景**：6000 步轻量认知体 + 6000 次行为选择 + 2000 次记忆写入洪峰。
**轻量档是必测项** —— 安装包（无 torch）跑的就是 `pasm.light.PASMAgent`，
它才是用户机器上真实运行的那条路径，所以装了 torch 也照测不误。

**断言（13 条）**：性能不衰减（后 20% vs 前 20%）· 人格不饱和钉死（两档都测）·
情绪不发散 · 行为熵不塌缩 · **状态往返一字不差** · **存档往返一字不差** ·
记忆库触顶不增长 · 峰值内存

## 四、守门层（原有）

| 智能体 | 职责 |
|---|---|
| `core-verifier` | 核心全量体检：引擎契约 / 认知层落盘 / 符号闭环 / 学习层两档 / 环境插件 / 安全底线探查 / 冒烟 |
| `parity-guard` | Studio 与核心的认知层必须逐字一致 —— 防"只在桌面端改、核心没落盘" |
| `regression` | 与事实基线比对，抓文件被删 / 模块消失 / 契约回退这类静默退化 |

## 五、这些智能体已经抓到的真问题

首轮跑下来，四个领域智能体一共压出 **6 个核心真问题**，其中 3 个当场修掉：

| # | 问题 | 严重度 | 处理 |
|---|---|---|---|
| 1 | `memory_layers.recall_layers` 同分记忆排序时元组退化到比较 `dict`，**直接抛 TypeError**（累计 60 条必现） | 崩溃 | ✅ 修（改按 key 排序） |
| 2 | 容量触顶后裁剪**不区分重要度**，"玩家救了我"与"吃面包"同权被丢 | 高 | ✅ 修（`episode_push(salience=)` + 按重要度淘汰，向后兼容） |
| 3 | `learning.feedback()` 只能加强"当前最偏好的动作"，**无法指定刚做的动作** —— 陪伴/教学场景没法说"夸的是这件事" | 高 | ✅ 修（加 `action=` 参数，向后兼容） |
| 4 | 跨表述检索基本失效：`memvec` 与 `recall_layers` 都是**字面匹配**。老人问"我叫什么名字"，记忆里存的是"姓名"，问不出来（实测 0.5 命中） | 中高 | ⏸ 报告 + 建议（需真实语义向量或 LLM query 改写） |
| 5 | 学习层**没有时间衰减**：停练 25 天的知识点与昨天练的一样强，长期学情会失真 | 中高 | ⏸ 报告 + 建议 |
| 6 | 人格在长期单向相处下**饱和钉死在边界**（仿生档 6000 步后 `[1.0, 1.0, 1.0]`），此后不可塑 | 中 | ⏸ 报告 + 建议（改动会影响产品手感，需产品决策） |
| 7 | `regression` 自身缺陷：**没有锁定解释器档位**。PASM-Lite 的具体引擎要 `import pasm_lite`（依赖 torch）才注册，换个解释器清单就从 `['pasm','pasm-light']` 变成 `[]`，被误报成 `[FAIL] 能力消失` | 中（**验证器自己失真**） | ✅ 修（基线记录 `python`+`torch`，档位不同时降级为 `WARN 档位不同·不可比`；并统一 `RepoContext.python()` 与领域场景共用同一套择优逻辑） |
| 8 | `regression` 自身缺陷：**指纹哈希没归一化行尾**。镜像仓 `git reset --hard` 后同一份文件变 CRLF，被报成 `[WARN] 核心认知层 文件有变更` | 低（又是**假红**） | ✅ 修（哈希前 `\r\n`→`\n`，口径与 `parity-guard` 对齐） |

> 第 7 条值得单独说：**验证器自己也会有 bug，而且它的 bug 最危险** ——
> 因为它输出的是一条听起来很确定的 `[FAIL]`。
> 一个"总报假红"的验证器会让人开始忽略它，比没有验证器更糟。
> 这也是为什么 `[SKIP]` 被当成一等公民、为什么降级必须写进结论。

> 第 4/5/6 条**故意没有擅自修**。它们改变的是产品行为（检索策略、学情模型、人格动力学），
> 属于设计决策而不是缺陷修复 —— 智能体的职责是把事实和证据摆清楚。

## 六、自己加一个

```python
# my_agents/my_check.py
from pasm_skills import Agent, register, scenarios as S


@register
class MyAgent(Agent):
    name = "my-check"
    goal = "一句话说清它替你把关什么"
    needs = ("core",)

    def run(self):
        python, torch_ok = S.choose_python(self.ctx, prefer_torch=True)
        res = S.run_scenario(self.ctx, MY_BODY, python=python, timeout=600)
        m = S.metrics_of(res)
        if not m:
            self.fail("场景未能运行", S.failure_detail(res))
            return None
        S.judge(self, m, SPEC)
        return None
```

```bash
PASM_SKILLS_PATH=./my_agents python -m pasm_skills run my-check
```

`S.run_scenario()` 会自动带上 PRELUDE，里面已经有好用的裸函数：
`emit / entropy / norm_entropy / tv_distance / topk_by / hits_in / ghost_max /
bounded / max_jump / span / mean / slope / rate / temp_layers / cleanup / TORCH_OK`。

**唯一红线**：场景必须驱动真实核心组件。核心组件拿不到时，
正确做法是 `SKIP` 并说明原因，而不是换个假的接着跑。

## Seven agents at a glance (English summary)

`pasm-skills` turns "long-term verification of the PASM cognitive engine" into
repeatable, dependency-free agents that emit structured findings (JSON-archivable,
baseline-diffable).

- **Gatekeepers** — `core-verifier` (full structural sweep), `parity-guard`
  (byte-for-byte parity between the core and Studio cognitive layers),
  `regression` (fact-baseline diffing).
- **Domain agents** — `npc-lifelong` (90 in-game days: memory retention,
  emotion dynamics, behavioural variety, persona stability), `companion-elderly`
  (30 days: key-fact retention is FAIL-level, colloquial retrieval is WARN-level,
  mood recovery, plain language), `study-tutor` (30 days: reinforcement,
  forgetting curve, similar-question recall, explainable learning state),
  `soak-longrun` (6000 steps: performance decay, persona saturation, save/load
  round-trip, memory growth).

Every scenario runs against **real core components** in an isolated subprocess.
When the core can't provide something, the agent reports `SKIP` with the reason —
it never substitutes a fake stand-in. Degrading from the bionic (torch) tier to the
lightweight tier is always printed on each finding, never hidden.

On their first run these agents surfaced **7 real issues**: three fixed in the core
(same-score sort crash, salience-blind memory eviction, `feedback()` unable to target a
specific action), three deliberately left as product decisions (cross-paraphrase
retrieval, missing forgetting curve, persona saturation), and one in the verifier
itself — `regression` was not pinning the interpreter tier, so switching interpreters
turned "Lite engines registered under torch" into a **false `FAIL: capability lost`**.
A verifier that cries wolf is worse than no verifier, which is why tier mismatches now
degrade to an explicit `WARN (tiers differ, not comparable)`.
