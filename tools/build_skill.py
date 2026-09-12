"""把 `skill/SKILL.body.md` 打包成两个平台可直接上传的技能包。

为什么要一个脚本
----------------
WorkBuddy 开放平台与 ClawHub 的 frontmatter 要求**不一样**，
但正文是同一份。手抄两份必然漂移，所以：

    skill/SKILL.body.md      ← 唯一正文（人工维护）
        │
        ├─ 拼 WorkBuddy frontmatter → dist/workbuddy/skills/<name>/SKILL.md
        └─ 拼 ClawHub frontmatter   → dist/clawhub/<name>/SKILL.md

用法：
    python tools/build_skill.py                 # 只生成目录
    python tools/build_skill.py --zip           # 顺带打 ZIP（WorkBuddy 上传用）

版本号取自 `pyproject.toml`，两边永远一致。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BODY = ROOT / "skill" / "SKILL.body.md"
DIST = ROOT.parent / "pasm-skills-dist"

#: 技能名 —— 两个平台都要求小写 + 短横线（ClawHub 正则是 ^[a-z0-9][a-z0-9-]*$）
NAME = "pasm-longterm-verify"

WORKBUDDY_DESC_ZH = (
    "PASM 长期验证智能体工坊——用可重复运行的智能体回答「认知引擎跑久了还是好的吗」。"
    "当需要验证记忆会不会丢、情绪会不会漂、行为会不会僵化、长期陪伴功能能不能上、"
    "或要在 CI/定时任务里对认知引擎做结构与行为双重体检时使用。"
    "关键词：PASM、长期验证、智能体、记忆保持、情绪漂移、人格饱和、遗忘曲线、"
    "soak 长跑、回归基线、parity 校验、core-verifier、npc-lifelong、companion-elderly、"
    "study-tutor、soak-longrun。"
)

WORKBUDDY_DESC_EN = (
    "PASM long-term verification agents - repeatable, dependency-free agents that answer "
    "\"is the cognitive engine still healthy after long runs?\". Use when checking memory "
    "retention, emotion drift, behavioural rigidity, long-run degradation, cross-repo parity, "
    "or when adding structural + behavioural health checks to CI."
)

CLAWHUB_DESC = (
    "Long-term verification agents for the PASM cognitive engine. Answers \"is it still healthy "
    "after long runs?\" with repeatable, stdlib-only checks: memory retention and salience-aware "
    "eviction, emotion drift, behavioural entropy collapse, persona saturation, forgetting curve, "
    "6000-step soak degradation, and cross-repo parity. Scenarios drive the real engine in an "
    "isolated subprocess and emit JSON-archivable, baseline-diffable findings."
)


def read_version() -> str:
    txt = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', txt, re.MULTILINE)
    if not m:
        raise SystemExit("pyproject.toml 里找不到 version")
    return m.group(1)


def frontmatter(platform: str, version: str) -> str:
    if platform == "workbuddy":
        # 开放平台必填：description / description_zh / description_en / version / author
        return (
            "---\n"
            "name: %s\n"
            "display_name: \"PASM 长期验证智能体\"\n"
            "display_name_en: \"PASM long-term verification agents\"\n"
            "description: %s\n"
            "description_zh: %s\n"
            "description_en: %s\n"
            "version: %s\n"
            "author: arronzheng\n"
            "license: MIT\n"
            "homepage: https://github.com/arronJack/pasm-skills\n"
            "repository: https://gitee.com/arronzheng/pasm-skills\n"
            "tags: [pasm, verification, agent, memory, long-run, soak-test]\n"
            "requires:\n"
            "  bins: [python3, git]\n"
            "  python: \">=3.10\"\n"
            "---\n"
        ) % (NAME, ind(WORKBUDDY_DESC_ZH), ind(WORKBUDDY_DESC_ZH),
             ind(WORKBUDDY_DESC_EN), version)
    # ClawHub：name ^[a-z0-9][a-z0-9-]*$ / version semver / metadata.openclaw.requires
    return (
        "---\n"
        "name: %s\n"
        "description: %s\n"
        "version: %s\n"
        "license: MIT-0\n"
        "author: arronzheng\n"
        "homepage: https://github.com/arronJack/pasm-skills\n"
        "metadata:\n"
        "  openclaw:\n"
        "    category: developer-tools\n"
        "    tags: [testing, verification, ai-agents, memory, long-running]\n"
        "    requires:\n"
        "      bins: [python3, git]\n"
        "      env: []\n"
        "---\n"
    ) % (NAME, ind(CLAWHUB_DESC), version)


def ind(text: str, pad: str = "  ") -> str:
    """把描述折成 YAML 的 `>-` 块。

    **中文不折行**：`>-` 会把换行折叠成空格，中文句子被折开后会多出一个突兀的空格
    （"会不会 丢、"）。YAML 允许超长单行，所以中文整体输出一行。
    """
    body = text.strip()
    if any(ord(ch) > 0x2E80 for ch in body):
        return ">-\n" + pad + body
    return ">-\n" + "\n".join(pad + line for line in wrap(body, 100))


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


def build(do_zip: bool) -> int:
    version = read_version()
    body = BODY.read_text(encoding="utf-8")
    # 正文里的版本占位（若有）也一并替换
    body = body.replace("{{VERSION}}", version)

    targets = {
        "workbuddy": DIST / "workbuddy" / "skills" / NAME / "SKILL.md",
        "clawhub": DIST / "clawhub" / NAME / "SKILL.md",
    }
    for platform, path in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(frontmatter(platform, version) + "\n" + body,
                        encoding="utf-8")
        print("[OK]   %-10s -> %s" % (platform, path))

    if do_zip:
        zip_path = DIST / ("%s-%s.zip" % (NAME, version))
        root = DIST / "workbuddy"          # ZIP 内为 skills/<name>/SKILL.md
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(root).as_posix())
        size = zip_path.stat().st_size
        print("[OK]   zip        -> %s（%.1f KB，上限 3MB）"
              % (zip_path, size / 1024.0))
        if size > 3 * 1024 * 1024:
            print("[FAIL] ZIP 超过 3MB —— WorkBuddy 开放平台会拒收", file=sys.stderr)
            return 1
        with zipfile.ZipFile(zip_path) as zf:
            print("       zip 内容：%s" % ", ".join(zf.namelist()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="打包双平台技能包")
    ap.add_argument("--zip", action="store_true", help="顺带打 WorkBuddy 上传用的 ZIP")
    ap.add_argument("--clean", action="store_true", help="先清空 dist（默认增量覆盖）")
    args = ap.parse_args(argv)
    if args.clean and DIST.exists():
        shutil.rmtree(DIST, ignore_errors=True)
    return build(args.zip)


if __name__ == "__main__":
    raise SystemExit(main())
