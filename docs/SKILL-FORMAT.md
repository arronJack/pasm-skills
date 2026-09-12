# 技能包格式（SKILL-FORMAT）

技能包 = **一份正文** + **两种归档形态**。平台会变，归档结构不会 —— 所以这里按**结构**命名，
不按平台名。

---

## 一、为什么是"一个正文、两种形态"

两种目标平台的硬要求**不一样**，而且**互相冲突**：

| 形态 | 归档结构 | frontmatter | 放错了会怎样 |
|---|---|---|---|
| `zip-root` | ZIP 里**根目录直接是 `SKILL.md`** | 完整（display_name / description_zh / description_en / author / requires） | 报「压缩包缺少 SKILL.md 文件」——它不递归找 |
| `slug-dir` | 以 slug 命名的**目录**，目录里放 `SKILL.md` | 最小（name / description / version / license / metadata） | 识别不到技能名 |

正文只有一份（`skill/SKILL.<name>.body.md`），元信息由打包库自动拼 ——
**手抄两遍必然漂移**，所以这件事交给 `pasm_skills.build`。

> 2026-09-12 实测：把 ZIP 包成 `skills/<name>/SKILL.md` 会被平台直接拒收。
> 这条坑已经写进打包库的结构自检里，改不回去。

---

## 二、目录约定（在智能体仓里）

```
your-repo/
├── pyproject.toml                  # version 是唯一来源（两种形态共用）
├── skill/                          # 只放正文，不放元信息
│   ├── SKILL.my-agent.body.md
│   └── SKILL.another.body.md
└── tools/
    └── build_skill.py              # 声明 SKILLS 列表，调用 run_cli
```

---

## 三、`tools/build_skill.py` 怎么写

```python
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pasm_skills.build import ProjectMeta, SkillSpec, run_cli

META = ProjectMeta(
    author="you",
    homepage="https://github.com/you/your-repo",
    repository="https://gitee.com/you/your-repo",
    license="MIT",
    requires_bins=["python3", "git"],
    requires_python=">=3.10",
)

SKILLS = [
    SkillSpec(
        name="my-agent",                     # 必须匹配 ^[a-z0-9][a-z0-9-]*$
        body_file="SKILL.my-agent.body.md",
        display_name_zh="我的智能体",
        display_name_en="My agent",
        desc_zh="……（中文，含触发词）",
        desc_en="……",
        plain_desc="……（英文，最小形态用）",
        plain_category="agents",
        plain_tags=["pasm", "my-agent"],
        plain_license="MIT-0",               # 部分平台强制 MIT-0
    ),
]

if __name__ == "__main__":
    raise SystemExit(run_cli(SKILLS, META, root=ROOT))
```

命令行：

```bash
python tools/build_skill.py                      # 构建全部
python tools/build_skill.py --name my-agent      # 只构建一个
python tools/build_skill.py --zip                # 顺带打 ZIP
python tools/build_skill.py --zip --clean        # 旧产物先挪到 _stale/
```

`--clean` 是**挪走**而不是删掉 —— 上一版包留着可对比，也避开某些环境对删除动作的安全守卫。

---

## 四、产物长什么样

```
<repo>-dist/
├── zip-root/
│   └── my-agent/SKILL.md          # 完整 frontmatter
├── slug-dir/
│   └── my-agent/SKILL.md          # 最小 frontmatter
└── my-agent-0.4.0.zip             # 内含且仅含 SKILL.md
```

自检（打包库内置，不通过直接 `[FAIL]` 退出）：

- ZIP 内容必须**恰好**是 `["SKILL.md"]`；
- ZIP 大小 ≤ 3MB。

---

## 五、frontmatter 长什么样

### 完整形态（`zip-root`）

```yaml
---
name: my-agent
display_name: "我的智能体"
display_name_en: "My agent"
description: >-
  ……（中文描述必须包含"什么时候用"+ 触发词，这是被检索到的关键）
description_zh: >-
  ……（同上）
description_en: >-
  ... (English)
version: 0.4.0
author: you
license: MIT
homepage: https://github.com/you/your-repo
repository: https://gitee.com/you/your-repo
tags: [pasm, agent, my]
requires:
  bins: [python3, git]
  python: ">=3.10"
---
```

### 最小形态（`slug-dir`）

```yaml
---
name: my-agent
description: >-
  ... (English, single paragraph)
version: 0.4.0
license: MIT-0
author: you
homepage: https://github.com/you/your-repo
metadata:
  openclaw:
    category: agents
    tags: [pasm, my-agent]
    requires:
      bins: [python3, git]
      env: []
---
```

> ⚠️ 中文描述**不折行**。YAML 的 `>-` 会把换行折叠成空格，中文句子被折开后会多出一个
> 突兀的空格（"会不会 丢、"）。打包库对中文特判为单行输出，别改回去。

> ⚠️ `license` 在最小形态里可能是 **MIT-0**（比 MIT 更宽松，**允许无署名使用**）。
> 部分平台强制这个许可证 —— 发布前确认你接受。

---

## 六、正文怎么写

正文是**给智能体读的说明书**，不是宣传页。骨架（`templates/SKILL.template.body.md`）：

1. 一句话说清是什么 + 硬约束（零 LLM 依赖 / 断网可用 / …）
2. **一段能直接跑的最小示例**（不是伪代码）
3. 什么时候用（写"需要 XX 时用"，不写"功能强大"）
4. 铁律（违反会怎样）
5. 核心 API（**每个示例都要实跑过**）
6. 交互模式命令表
7. 档位与降级
8. **已知短板**（这一节不能省 —— 做不到的说清楚，比假装能做到更可信）
9. 接入自己产品的片段

---

## 七、发布前自检

```bash
python tools/build_skill.py --zip --clean
python -c "
import zipfile, glob, os
for z in sorted(glob.glob('../*-dist/*.zip')):
    print(os.path.basename(z), zipfile.ZipFile(z).namelist())
"
# 期望每个都是 ['SKILL.md']
```

清单：

- [ ] 每个 ZIP 的内容恰好是 `['SKILL.md']`
- [ ] 每个 ZIP ≤ 3MB
- [ ] `name` 匹配 `^[a-z0-9][a-z0-9-]*$`
- [ ] 中文描述不折行、含触发词
- [ ] 正文里的 API 与签名**真实存在**（实跑过）
- [ ] 最小形态的 `license` 与源码仓的差异是**有意的**，且你接受
