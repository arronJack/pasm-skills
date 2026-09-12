> 本文件是 **SKILL.md 的正文部分**（不含 frontmatter）。
> `tools/build_skill.py` 会把它分别拼上两种归档形态的 frontmatter（`zip-root` / `slug-dir`），产出可直接上传的包。
> 之所以拆开：正文只有一份，两个平台的元数据要求不同，分开维护必然漂移。

# PASM 长期验证智能体工坊

用**可重复运行的智能体**回答一个问题：**"认知引擎跑久了，还是好的吗？"**

## 什么时候用

- 改了记忆 / 情绪 / 人格 / 学习层之后，想知道有没有**悄悄跑偏**（而不是等用户真机反馈）；
- 要判断一个"长期陪伴型"功能能不能上：记不记得住、情绪会不会漂、行为会不会僵；
- 需要在 CI / 定时任务里，对认知引擎持续做**结构体检 + 行为体检**；
- 想自己加一个领域智能体（新场景：客服、教学、NPC、老人陪伴…）。

## 0. 铁律

1. **零依赖**：只用 Python 标准库。不需要 torch、不需要 GPU、不需要 API key、**不需要服务器**。
   验证器一旦有依赖，就会在最需要它的时候跑不起来。
2. **结论只由代码事实决定**，不引入 LLM 的不确定性 —— 避免"AI 说没问题"式的假安全感。
3. **场景必须驱动真实核心组件**。拿不到就报 `SKIP` 并写清原因；
   **绝不允许**在验证器里手搓一个"看起来像"的替身。**假绿比没查更危险。**
4. **降级必须可见**。装了 torch 跑仿生档、没装降级轻量档 ——
   这个档位要**写进每一条结论**，不许在暗处换实现。
5. **只读**。校验绝不修改被检查的仓库，只写自己的 `baselines/`。

## 1. 装上并定位

```bash
git clone https://github.com/arronJack/pasm-skills.git
cd pasm-skills
python -m pasm_skills list          # 看三仓定位 + 智能体清单
```

装成命令也行：

```bash
pip install -e .
pasm-skills list
```

被检查的三个仓默认按约定路径找，也可显式指定：

```bash
export PASM_CORE=/path/to/PASM          # 核心包（pasm/）
export PASM_STUDIO=/path/to/pasm_qclaw  # 桌面端仓（desktop/）
export PASM_LITE=/path/to/PASM_LITE     # 教学版
export PASM_SKILLS_ROOTS=/extra/root    # 兜底：在这些目录下按名找
```

解释器选择（**这一步决定跑哪一档**）：

```bash
export PASM_PYTHON=/path/to/python        # 最高优先，显式钉死
export PASM_TORCH_PYTHON=/path/to/python  # 指定"带 torch"的解释器，优先用于仿生档
```

不设时，框架会自己挑一个能 `import torch` 的解释器；挑不到就降级轻量档并如实标注。

## 2. 跑什么

```bash
python -m pasm_skills run core-verifier        # 结构：契约 / 认知层落盘 / 符号闭环 / 插件 / 安全底线 / 冒烟
python -m pasm_skills run parity-guard         # 结构：核心仓 ↔ Studio 仓认知层逐字一致
python -m pasm_skills run npc-lifelong         # 行为：90 天 NPC 长期生命
python -m pasm_skills run companion-elderly    # 行为：30 天独居老人陪伴（安全关键）
python -m pasm_skills run study-tutor          # 行为：30 天学习陪伴
python -m pasm_skills run soak-longrun         # 行为：6000 步长效耐久（约 20s）
python -m pasm_skills run regression           # 对比事实基线，抓静默退化
python -m pasm_skills run --all                # 全跑一遍（约 1.5 分钟）
```

常用参数：

```bash
--json --out report.json     # 归档结论（含场景原始指标，可前后对比）
--quiet                      # 只显示非 OK 结论
--all                        # 全部智能体
```

**退出码**：`0` 全通过 · `1` 有 FAIL · `2` 用法或定位错误 —— 可直接接 CI。

## 3. 怎么读结论

四级：`[OK]` 通过 · `[WARN]` 值得看一眼 · `[FAIL]` 必须处理 · `[SKIP]` 条件不足跳过。

- `[WARN]` **不等于失败**。有些 WARN 是**真实的产品能力短板**（例："停练的知识点不衰减"
  = 学习层没有遗忘机制）。这时候要做的是**产品决策**，不是改验证器把灯弄绿。
- `[SKIP]` 的 detail **一定要读** —— 它说明"这次没查成"，不是"查了没问题"。
- 结论里的 `[仿生层 torch]` / `[轻量档]` 标注，说明这条是用哪一档跑的。
  **两档结论不能混着比。**

判断"有没有退化"看 `regression`：它把认知层文件指纹、引擎清单、契约版本存成基线，
下次运行逐项比对。基线与本次**解释器档位不同**时，清单类结论会降级为
`[WARN] 档位不同·不可比`（这不是退化，是换了把尺子）。

## 4. 加一个新智能体

写在任意目录，用 `PASM_SKILLS_PATH` 指过去即可：

```python
# my_agents/api_guard.py
from pasm_skills.agent import Agent, register

@register
class ApiGuardAgent(Agent):
    """守护核心公开 API 不许擅自增删。"""
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
PASM_SKILLS_PATH=./my_agents python -m pasm_skills run api-guard
```

`self.ctx.probe(仓键, 代码)` 在**独立子进程**里、以该仓为 cwd 执行代码
（三个仓有同名模块，同进程 import 会互相顶掉）。

### 写"行为验证"型智能体

用 `pasm_skills.scenarios`，它管住最麻烦的三件事：

```python
from pasm_skills import scenarios as sc

python, torch_ok = sc.choose_python(self.ctx)            # 1) 选解释器（优先带 torch）
res = sc.run_scenario(self.ctx, body, python=python)     # 2) 隔离跑场景，回传 JSON 指标
sc.judge(self, sc.metrics_of(res), MY_SPEC, tier=tier)   # 3) 按阈值表批量判 OK/WARN/FAIL
```

阈值表每项：`{"key","title","lo","hi","bad","fmt","note"}`。
越界默认记 `WARN`；`bad="fail"` 表示越界**必须**算 `FAIL`
（用于安全关键项，如"老人用药事实检索不出来"）。
拿到的 `metrics` 存进 `self.extra`，会随归档 JSON 落盘 —— **长期验证要的就是可比性**。

`PRELUDE` 已注入这些裸函数，场景里直接用：
`emit / entropy / norm_entropy / tv_distance / topk_by / hits_in / ghost_max /
bounded / max_jump / span / mean / slope / rate / temp_layers / cleanup / TORCH_OK`。

## 5. 排查

| 症状 | 原因 | 处理 |
|---|---|---|
| `[SKIP] 仓库 core 未找到` | 路径没定到 | 设 `PASM_CORE` 或 `PASM_SKILLS_ROOTS` |
| 结论全是 `[轻量档]` | 没找到带 torch 的解释器 | 设 `PASM_TORCH_PYTHON` 或 `PASM_PYTHON` |
| `[WARN] 档位不同·不可比` | 基线与本次解释器不同 | 用 `PASM_PYTHON` 固定解释器后 `regression --update` 重建基线 |
| `[FAIL] ... 文件被移除` | 真的删了文件 | 看 detail 里的文件名，回核心仓确认 |
| 场景 `[SKIP] 场景未产出该指标` | 场景代码抛异常 | 加 `--json` 看 `extra`，或直接手跑那段场景代码 |

重建基线（**只在确认当前状态正确时做**）：

```bash
python -m pasm_skills run regression --update
```

## 6. 它已经抓到的真问题（为什么值得跑）

上线首轮就压出 7 个躺在核心或验证器自己的问题：

| # | 问题 | 处理 |
|---|---|---|
| 1 | `recall_layers` 同分记忆排序时元组退化到比较 `dict`，**直接抛 TypeError**（60 条同分必现） | ✅ 修 |
| 2 | 记忆容量触顶裁剪**不区分重要度**，"玩家救了我"与"吃面包"同权被丢 | ✅ 修（`salience`） |
| 3 | `feedback()` 无法指定"刚做的动作"，陪伴/教学场景没法说"夸的是这件事" | ✅ 修（`action=`） |
| 4 | 跨表述检索失效：口语问句命中率约 0.5（字面匹配） | ⏸ 产品决策 |
| 5 | 学习层无遗忘曲线：停练 25 天与昨天练的一样强 | ⏸ 产品决策 |
| 6 | 人格长期单向相处后饱和钉死在 ±1，此后不可塑 | ⏸ 产品决策 |
| 7 | `regression` 未锁定解释器档位，把"换了解释器"误报成 `[FAIL] 能力消失` | ✅ 修 |

第 7 条最值得记住：**验证器自己也会有 bug，而且它的 bug 最危险** ——
一个"总报假红"的验证器会让人开始忽略它，比没有验证器更糟。

## License

MIT © arronZheng（小志）。仓库：<https://github.com/arronJack/pasm-skills>
