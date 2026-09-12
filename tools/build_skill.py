"""把 `skill/SKILL.<name>.body.md` 打包成两个平台可直接上传的技能包。

为什么要一个脚本
----------------
两种目标平台的 frontmatter 要求**不一样**，**归档结构也不一样**，
但正文是同一份。手抄必然漂移，所以：

    skill/SKILL.<name>.body.md      ← 唯一正文（人工维护）
        │
        ├─ 拼「完整元信息」frontmatter → dist/zip-root/<name>/SKILL.md
        └─ 拼「最小元信息」frontmatter → dist/slug-dir/<name>/SKILL.md

两个形态按**归档结构**命名，而不是按平台名 —— 平台名会变，结构不会：

| 形态 | 归档结构 | frontmatter |
|---|---|---|
| `zip-root` | ZIP 里**根目录直接是 `SKILL.md`** | 完整（display_name / description_zh / description_en / author / requires） |
| `slug-dir` | 以 slug 命名的**目录**，目录里放 `SKILL.md` | 最小（name / description / version / license / metadata） |

归档结构（**实测踩坑，别改**）
-----------------------------
`zip-root` 平台要求 **`SKILL.md` 直接躺在 ZIP 根目录**。
包成 `skills/<name>/SKILL.md` 会被拒收，报「压缩包缺少 SKILL.md 文件」——
平台只认根目录，不递归找。（2026-09-12 实测，首次提交时踩到。）

`slug-dir` 反过来，要的是**以 slug 命名的目录**，目录里放 SKILL.md。

> 形态 ↔ 具体平台的对应关系、各平台的登录方式与审核流程，
> 记在**仓库外**的本机发布指南里（`pasm-skills-dist/PUBLISH.local.md`），
> 不随公开仓分发。

用法：
    python tools/build_skill.py                       # 构建所有 skill
    python tools/build_skill.py --name pasm-agents    # 只构建某一个
    python tools/build_skill.py --zip                 # 顺带打 ZIP（zip-root 形态上传用）
    python tools/build_skill.py --zip --clean         # 先把旧产物挪到 _stale/

版本号取自 `pyproject.toml`，两个形态永远一致。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT.parent / "pasm-skills-dist"

#: 两个归档形态（目录名 = 形态名）
LAYOUT_ZIPROOT = "zip-root"
LAYOUT_SLUGDIR = "slug-dir"


# ============================================================ 技能清单


@dataclass
class SkillSpec:
    name: str
    body_file: str                 # 相对 skill/ 的文件名
    display_name_zh: str
    display_name_en: str
    desc_zh: str                   # 完整形态：中文描述
    desc_en: str                   # 完整形态：英文描述
    plain_desc: str                # 最小形态：描述（英文）
    plain_category: str
    plain_tags: List[str]
    plain_license: str             # 最小形态的平台可能强制 MIT-0；完整形态用 MIT


SKILLS: List[SkillSpec] = [
    SkillSpec(
        name="pasm-longterm-verify",
        body_file="SKILL.verify.body.md",
        display_name_zh="PASM 长期验证智能体",
        display_name_en="PASM long-term verification agents",
        desc_zh=(
            "PASM 长期验证智能体工坊——用可重复运行的智能体回答「认知引擎跑久了还是好的吗」。"
            "当需要验证记忆会不会丢、情绪会不会漂、行为会不会僵化、长期陪伴功能能不能上、"
            "或要在 CI/定时任务里对认知引擎做结构与行为双重体检时使用。"
            "关键词：PASM、长期验证、智能体、记忆保持、情绪漂移、人格饱和、遗忘曲线、"
            "soak 长跑、回归基线、parity 校验、core-verifier、npc-lifelong、companion-elderly、"
            "study-tutor、soak-longrun。"
        ),
        desc_en=(
            "PASM long-term verification agents - repeatable, dependency-free agents that answer "
            "\"is the cognitive engine still healthy after long runs?\". Use when checking memory "
            "retention, emotion drift, behavioural rigidity, long-run degradation, cross-repo parity, "
            "or when adding structural + behavioural health checks to CI."
        ),
        plain_desc=(
            "Long-term verification agents for the PASM cognitive engine. Answers \"is it still healthy "
            "after long runs?\" with repeatable, stdlib-only checks: memory retention and salience-aware "
            "eviction, emotion drift, behavioural entropy collapse, persona saturation, forgetting curve, "
            "6000-step soak degradation, and cross-repo parity. Scenarios drive the real engine in an "
            "isolated subprocess and emit JSON-archivable, baseline-diffable findings."
        ),
        plain_category="developer-tools",
        plain_tags=["testing", "verification", "ai-agents", "memory", "long-running"],
        plain_license="MIT-0",
    ),
    SkillSpec(
        name="pasm-agents",
        body_file="SKILL.agents.body.md",
        display_name_zh="PASM 产品智能体",
        display_name_en="PASM product agents",
        desc_zh=(
            "PASM 产品智能体——基于 PASM 引擎、可立即装载使用的智能体（游戏 NPC / 老人陪伴 / 学习陪伴）。"
            "当需要给游戏加一个有记忆有情感的 NPC、给独居老人做关键事实记忆与危机升级陪伴、"
            "给学生做薄弱点定位与巩固建议，或要在自己的产品里嵌入 PASM 引擎能力时使用。"
            "零 LLM 依赖、断网可用、状态可持久化；pip install 完直接 import。"
            "关键词：PASM、智能体、NPC、老人陪伴、学习陪伴、记忆、情绪、危机升级、"
            "pasm-agents、NpcAgent、ElderlyCompanion、LearningTutor、agent 工厂。"
        ),
        desc_en=(
            "PASM product agents - ready-to-use agents built on the PASM cognitive engine: "
            "game NPCs with memory and emotion, elderly companions with key-fact retrieval and "
            "crisis escalation, and learning tutors with weak-topic localisation. "
            "Zero LLM dependency, offline-runnable, state persists to ~/.pasm-agents/<id>/. "
            "Use when you need to drop a sentient NPC into a game, build an elderly-care assistant, "
            "or wire PASM capabilities into your own product. "
            "Keywords: pasm-agents, NpcAgent, ElderlyCompanion, LearningTutor, agent factory, "
            "memory, emotion, persona, salience-aware eviction, crisis escalation."
        ),
        plain_desc=(
            "Ready-to-use product agents built on the PASM cognitive engine. Three first-class "
            "agents ship in the box: NpcAgent (game NPCs with persistent memory, persona-weighted "
            "action selection, and salience-aware recall), ElderlyCompanion (key-fact retrieval at "
            "100% for medications/allergies/family, automatic crisis detection and escalation), and "
            "LearningTutor (EMA-tracked mastery per topic, weakest-first next-question selection, "
            "encouraging dialogue). All agents share a BaseAgent with persistent JSON state under "
            " ~/.pasm-agents/<id>/. Offline-runnable (no LLM required). Tier label is exposed on every "
            "agent so callers always know which engine path is live (light / core / bionic)."
        ),
        plain_category="agents",
        plain_tags=["ai-agents", "pasm", "npc", "companion", "tutor", "memory", "emotion"],
        plain_license="MIT-0",
    ),
]


# ============================================================ frontmatter 渲染


def read_version() -> str:
    txt = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', txt, re.MULTILINE)
    if not m:
        raise SystemExit("pyproject.toml 里找不到 version")
    return m.group(1)


def wrap(text: str, width: int) -> list:
    """按宽度折行（中文按 2 宽度算），尽量不破坏词。"""
    out, line, w = [], [], 0
    for token in re.findall(r"[A-Za-z0-9_\-\./,()\"'+:;=~@#%&*\[\]{}<>!?$\\|^`]+|\s+|.", text):
        tw = sum(2 if ord(ch) > 0x2E80 else 1 for ch in token)
        if w + tw > width and line:
            out.append("".join(line).rstrip() if token.strip() else "".join(line))
            line, w = [], 0
            if not token.strip():
                continue
        line.append(token)
        w += tw
    if line:
        out.append("".join(line).rstrip())
    return out or [""]


def ind(text: str, pad: str = "  ") -> str:
    """把描述折成 YAML 的 `>-` 块。

    **中文不折行**：`>-` 会把换行折叠成空格，中文句子被折开后会多出一个突兀的空格
    （"会不会 丢、"）。YAML 允许超长单行，所以中文整体输出一行。
    """
    body = text.strip()
    if any(ord(ch) > 0x2E80 for ch in body):
        return ">-\n" + pad + body
    return ">-\n" + "\n".join(pad + line for line in wrap(body, 100))


def frontmatter_full(spec: SkillSpec, version: str) -> str:
    """完整元信息形态（`zip-root`）。"""
    return (
        "---\n"
        "name: %s\n"
        "display_name: \"%s\"\n"
        "display_name_en: \"%s\"\n"
        "description: %s\n"
        "description_zh: %s\n"
        "description_en: %s\n"
        "version: %s\n"
        "author: arronzheng\n"
        "license: MIT\n"
        "homepage: https://github.com/arronJack/pasm-skills\n"
        "repository: https://gitee.com/arronzheng/pasm-skills\n"
        "tags: [pasm, agent, %s]\n"
        "requires:\n"
        "  bins: [python3, git]\n"
        "  python: \">=3.10\"\n"
        "---\n"
    ) % (
        spec.name, spec.display_name_zh, spec.display_name_en,
        ind(spec.desc_zh), ind(spec.desc_zh), ind(spec.desc_en),
        version, spec.name.replace("pasm-", ""),
    )


def frontmatter_plain(spec: SkillSpec, version: str) -> str:
    """最小元信息形态（`slug-dir`）。

    注意 `license` 用的是 `plain_license`（可能是 MIT-0）：**部分平台强制 MIT-0**
    —— 比 MIT 还宽松，允许无署名使用。发布前确认是否接受该条款。
    """
    tags_yaml = "[" + ", ".join(spec.plain_tags) + "]"
    return (
        "---\n"
        "name: %s\n"
        "description: %s\n"
        "version: %s\n"
        "license: %s\n"
        "author: arronzheng\n"
        "homepage: https://github.com/arronJack/pasm-skills\n"
        "metadata:\n"
        "  openclaw:\n"
        "    category: %s\n"
        "    tags: %s\n"
        "    requires:\n"
        "      bins: [python3, git]\n"
        "      env: []\n"
        "---\n"
    ) % (
        spec.name, ind(spec.plain_desc),
        version, spec.plain_license,
        spec.plain_category, tags_yaml,
    )


# ============================================================ 构建


def build(spec: SkillSpec, version: str, do_zip: bool) -> int:
    body_path = ROOT / "skill" / spec.body_file
    if not body_path.exists():
        print("[FAIL] %s 不存在" % body_path, file=sys.stderr)
        return 1
    body = body_path.read_text(encoding="utf-8").replace("{{VERSION}}", version)

    targets = {
        LAYOUT_ZIPROOT: DIST / LAYOUT_ZIPROOT / spec.name / "SKILL.md",
        LAYOUT_SLUGDIR: DIST / LAYOUT_SLUGDIR / spec.name / "SKILL.md",
    }
    for layout, path in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if layout == LAYOUT_ZIPROOT:
            text = frontmatter_full(spec, version) + "\n" + body
        else:
            text = frontmatter_plain(spec, version) + "\n" + body
        path.write_text(text, encoding="utf-8")
        print("[OK]   %-10s %-22s -> %s" % (layout, spec.name, path))

    if do_zip:
        zip_path = DIST / ("%s-%s.zip" % (spec.name, version))
        # zip-root 形态要求根目录直接是 SKILL.md，所以以该目录为归档根
        root = DIST / LAYOUT_ZIPROOT / spec.name
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(root).as_posix())
        size = zip_path.stat().st_size
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        print("[OK]   zip        %-22s -> %s（%.1f KB，限制 3MB）"
              % (spec.name, zip_path, size / 1024.0))
        print("       zip 内容：%s" % ", ".join(names))
        if names != ["SKILL.md"]:
            print("[FAIL] ZIP 内必须是且仅是根目录的 SKILL.md，当前：%s" % names,
                  file=sys.stderr)
            return 1
        if size > 3 * 1024 * 1024:
            print("[FAIL] ZIP 超过 3MB —— zip-root 形态的平台会拒收", file=sys.stderr)
            return 1
    return 0


def _clean_dist() -> None:
    """把上次的产物**挪到 `_stale/`**，而不是删掉。

    两个原因：
    1. 有些环境（含本机）对删除动作有安全守卫，`rmtree` 会被拦下，脚本直接中断；
    2. 产物本来就不该被静默销毁 —— 上一版包留着可对比，也方便回溯。
    """
    if not DIST.exists():
        return
    stale = DIST / "_stale"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for sub in (LAYOUT_ZIPROOT, LAYOUT_SLUGDIR):
        src = DIST / sub
        if not src.exists():
            continue
        stale.mkdir(parents=True, exist_ok=True)
        dst = stale / ("%s-%s" % (sub, stamp))
        try:
            shutil.move(str(src), str(dst))
            print("[INFO] 旧产物已挪到 %s" % dst)
        except Exception as ex:                       # noqa: BLE001
            print("[WARN] 挪动失败（继续构建）：%s" % ex, file=sys.stderr)


# ============================================================ main


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="打包两种归档形态的技能包（多个）")
    ap.add_argument("--zip", action="store_true",
                    help="顺带打上传用的 ZIP（zip-root 形态）")
    ap.add_argument("--clean", action="store_true", help="先把旧产物挪到 _stale/")
    ap.add_argument("--name", default=None,
                    help="只构建某个技能（缺省 = 全部）")
    args = ap.parse_args(argv)

    if args.clean:
        _clean_dist()

    version = read_version()
    rc = 0
    for spec in SKILLS:
        if args.name and spec.name != args.name:
            continue
        if build(spec, version, args.zip) != 0:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
