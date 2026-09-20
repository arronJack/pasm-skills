"""技能包打包库 —— 把智能体打成平台可直接上传的技能包。

为什么是一个"库"而不是一个脚本
------------------------------
基座仓自己不产出技能包，但**所有智能体仓都要打**。如果每个仓各抄一份脚本，
归档规则（尤其是那个踩过坑的 ZIP 结构）迟早漂移。所以规则留在这里，各仓只声明"我有哪些技能"。

一个正文 → 两种**归档形态**（按结构命名，不按平台名 —— 平台会变，结构不会）：

| 形态 | 归档结构 | frontmatter | 产物 |
|---|---|---|---|
| `zip-root` | ZIP **根目录直接是 `SKILL.md`** | 完整（display_name / description_zh / description_en / author / requires） | `dist/zip-root/<name>/SKILL.md` |
| `slug-dir` | 以 slug 命名的**目录**，目录内放 `SKILL.md` | 最小（name / description / version / license / metadata） | `dist/slug-dir/<name>/SKILL.md` |

归档结构（**实测踩坑，别改**）
-----------------------------
`zip-root` 形态的平台要求 **`SKILL.md` 直接躺在 ZIP 根目录**。
包成 `skills/<name>/SKILL.md` 会被拒收，报「压缩包缺少 SKILL.md 文件」——平台不递归找。
（2026-09-12 实测，首次提交时踩到。）

怎么用
------
在自己的仓写一个 `tools/build_skill.py`：

```python
from pasm_skills.build import ProjectMeta, SkillSpec, run_cli

META = ProjectMeta(
    author="arronzheng",
    homepage="https://github.com/arronJack/pasm-agents",
    repository="https://gitee.com/arronzheng/pasm-agents",
)
SKILLS = [
    SkillSpec(name="my-agent", body_file="SKILL.my.body.md", ...),
]

if __name__ == "__main__":
    raise SystemExit(run_cli(SKILLS, META))
```

命令行：

    python tools/build_skill.py                      # 构建全部
    python tools/build_skill.py --name my-agent      # 只构建一个
    python tools/build_skill.py --zip                # 顺带打 ZIP（zip-root 形态上传用）
    python tools/build_skill.py --zip --clean        # 先把旧产物挪到 _stale/

版本号取自 `pyproject.toml`，两种形态永远一致。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

#: 两个归档形态（目录名 = 形态名）
LAYOUT_ZIPROOT = "zip-root"
LAYOUT_SLUGDIR = "slug-dir"

#: 技能包大小上限（部分平台硬限制 3MB）
ZIP_MAX_BYTES = 3 * 1024 * 1024

#: 正文里**不许出现**的维护者内部注释。
#: 每条都对应一次真事故：早期四份正文开头都写着"本文件是 SKILL.md 的正文部分…"，
#: 那段**原样出现在平台上用户点开的技能页里**（ClawHub 实测，33 次下载都带着它）。
#: 维护者说明应该放各仓的 `skill/README.md`。不要随手放宽这个表。
BODY_FORBIDDEN = (
    ("SKILL.md 的正文部分", "给维护者看的构建注释"),
    ("build_skill.py 会把它", "给维护者看的构建注释"),
    ("产出可直接上传的包", "给维护者看的构建注释"),
)

#: 正文里不许出现的**个人环境路径**（公开产物分发给陌生人，不该带这些）
BODY_PATH_PATTERNS = (
    (re.compile(r"[A-Za-z]:[\\/]Users[\\/]", re.I), "Windows 个人目录绝对路径"),
    (re.compile(r"/home/[A-Za-z0-9_.-]+/"), "Linux 个人目录绝对路径"),
)


def lint_body(body: str, where: str) -> List[str]:
    """检查正文里有没有"不该发给陌生人"的内容。返回问题清单（空 = 干净）。

    为什么放在打包库、而不是各仓自己写检查脚本：**这里才是产物的唯一出口**。
    规则做进出口，所有用基座打包的仓（pasm-agents，或别人自己的仓）自动受保护，
    不必每个仓各抄一份。
    """
    problems: List[str] = []
    for marker, why in BODY_FORBIDDEN:
        if marker in body:
            problems.append("%s：正文含「%s」（%s）—— 它会原样出现在用户看到的技能页上"
                            % (where, marker, why))
    for pat, why in BODY_PATH_PATTERNS:
        m = pat.search(body)
        if m:
            problems.append("%s：正文含%s（%s…）—— 公开产物不该带个人环境信息"
                            % (where, why, m.group(0)))
    return problems


@dataclass
class ProjectMeta:
    """技能包 frontmatter 里与"谁发布的"有关的信息。"""
    author: str
    homepage: str = ""
    repository: str = ""
    license: str = "MIT"
    requires_bins: List[str] = field(default_factory=lambda: ["python3", "git"])
    requires_python: str = ">=3.10"


@dataclass
class SkillSpec:
    """一个技能的声明。"""
    name: str
    body_file: str                 # 相对 skill/ 的正文文件名
    display_name_zh: str
    display_name_en: str
    desc_zh: str                   # 完整形态：中文描述（同时作为通用 description）
    desc_en: str                   # 完整形态：英文描述
    plain_desc: str                # 最小形态：描述（英文）
    plain_category: str
    plain_tags: List[str]
    plain_license: str = "MIT-0"   # 最小形态的平台可能强制 MIT-0（比 MIT 更宽松，允许无署名）


# ============================================================ YAML 小工具


def read_version(root: Path) -> str:
    """从 `pyproject.toml` 读版本号（单一来源）。"""
    txt = (root / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', txt, re.MULTILINE)
    if not m:
        raise SystemExit("pyproject.toml 里找不到 version")
    return m.group(1)


def wrap(text: str, width: int) -> List[str]:
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


# ============================================================ frontmatter


def frontmatter_full(spec: SkillSpec, version: str, meta: ProjectMeta) -> str:
    """完整元信息形态（`zip-root`）。"""
    lines = [
        "---",
        "name: %s" % spec.name,
        'display_name: "%s"' % spec.display_name_zh,
        'display_name_en: "%s"' % spec.display_name_en,
        "description: %s" % ind(spec.desc_zh),
        "description_zh: %s" % ind(spec.desc_zh),
        "description_en: %s" % ind(spec.desc_en),
        "version: %s" % version,
        "author: %s" % meta.author,
        "license: %s" % meta.license,
    ]
    if meta.homepage:
        lines.append("homepage: %s" % meta.homepage)
    if meta.repository:
        lines.append("repository: %s" % meta.repository)
    lines += [
        "tags: [pasm, agent, %s]" % spec.name.replace("pasm-", ""),
        "requires:",
        "  bins: [%s]" % ", ".join(meta.requires_bins),
        '  python: "%s"' % meta.requires_python,
        "---",
        "",
    ]
    return "\n".join(lines)


def frontmatter_plain(spec: SkillSpec, version: str, meta: ProjectMeta) -> str:
    """最小元信息形态（`slug-dir`）。

    注意 `license` 用的是 `spec.plain_license`（可能是 MIT-0）：
    **部分平台强制 MIT-0** —— 比 MIT 还宽松，允许无署名使用。发布前确认是否接受。
    """
    tags_yaml = "[" + ", ".join(spec.plain_tags) + "]"
    lines = [
        "---",
        "name: %s" % spec.name,
        "description: %s" % ind(spec.plain_desc),
        "version: %s" % version,
        "license: %s" % spec.plain_license,
        "author: %s" % meta.author,
    ]
    if meta.homepage:
        lines.append("homepage: %s" % meta.homepage)
    lines += [
        "metadata:",
        "  openclaw:",
        "    category: %s" % spec.plain_category,
        "    tags: %s" % tags_yaml,
        "    requires:",
        "      bins: [%s]" % ", ".join(meta.requires_bins),
        "      env: []",
        "---",
        "",
    ]
    return "\n".join(lines)


# ============================================================ 构建


def build_one(spec: SkillSpec, version: str, meta: ProjectMeta, root: Path,
              dist: Path, do_zip: bool = False) -> int:
    """构建一个技能的两种形态（可选顺带打 ZIP）。返回 0 表示成功。"""
    body_path = root / "skill" / spec.body_file
    if not body_path.exists():
        print("[FAIL] %s 不存在" % body_path, file=sys.stderr)
        return 1
    body = body_path.read_text(encoding="utf-8").replace("{{VERSION}}", version)

    lint = lint_body(body, spec.body_file)
    if lint:
        for msg in lint:
            print("[FAIL] %s" % msg, file=sys.stderr)
        print("       打包中止 —— 这类内容发出去会直接暴露给用户，不是提醒是拦截。",
              file=sys.stderr)
        return 1

    targets = {
        LAYOUT_ZIPROOT: (dist / LAYOUT_ZIPROOT / spec.name / "SKILL.md",
                         frontmatter_full(spec, version, meta)),
        LAYOUT_SLUGDIR: (dist / LAYOUT_SLUGDIR / spec.name / "SKILL.md",
                         frontmatter_plain(spec, version, meta)),
    }
    for layout, (path, fm) in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fm + "\n" + body, encoding="utf-8")
        print("[OK]   %-10s %-24s -> %s" % (layout, spec.name, path))

    if not do_zip:
        return 0

    zip_path = dist / ("%s-%s.zip" % (spec.name, version))
    src_root = dist / LAYOUT_ZIPROOT / spec.name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(src_root.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(src_root).as_posix())
    size = zip_path.stat().st_size
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    print("[OK]   zip        %-24s -> %s（%.1f KB，限制 3MB）"
          % (spec.name, zip_path, size / 1024.0))
    print("       zip 内容：%s" % ", ".join(names))
    if names != ["SKILL.md"]:
        print("[FAIL] ZIP 内必须是且仅是根目录的 SKILL.md，当前：%s" % names, file=sys.stderr)
        return 1
    if size > ZIP_MAX_BYTES:
        print("[FAIL] ZIP 超过 3MB —— zip-root 形态的平台会拒收", file=sys.stderr)
        return 1
    return 0


def clean_dist(dist: Path) -> None:
    """把上次的产物**挪到 `_stale/`**，而不是删掉。

    两个原因：
    1. 有些环境（含本机）对删除动作有安全守卫，`rmtree` 会被拦下，脚本直接中断；
    2. 产物本来就不该被静默销毁 —— 上一版包留着可对比，也方便回溯。
    """
    if not dist.exists():
        return
    stale = dist / "_stale"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for sub in (LAYOUT_ZIPROOT, LAYOUT_SLUGDIR):
        src = dist / sub
        if not src.exists():
            continue
        stale.mkdir(parents=True, exist_ok=True)
        dst = stale / ("%s-%s" % (sub, stamp))
        try:
            shutil.move(str(src), str(dst))
            print("[INFO] 旧产物已挪到 %s" % dst)
        except Exception as ex:                      # noqa: BLE001
            print("[WARN] 挪动失败（继续构建）：%s" % ex, file=sys.stderr)
    # 根目录的上传用 ZIP 也要一起挪走 —— 否则新旧版本混在同一目录，
    # 上传时极易拿错文件（这正是"发出去的还是上一版"的经典成因）。
    old_zips = sorted(dist.glob("*.zip"))
    if old_zips:
        stale.mkdir(parents=True, exist_ok=True)
        zip_dir = stale / ("zips-%s" % stamp)
        zip_dir.mkdir(parents=True, exist_ok=True)
        for z in old_zips:
            try:
                shutil.move(str(z), str(zip_dir / z.name))
            except Exception as ex:                  # noqa: BLE001
                print("[WARN] 挪动 %s 失败（继续构建）：%s" % (z.name, ex), file=sys.stderr)
        print("[INFO] 旧 ZIP %d 个已挪到 %s" % (len(old_zips), zip_dir))


def build_all(specs: Sequence[SkillSpec], meta: ProjectMeta, root: Path,
              dist: Optional[Path] = None, do_zip: bool = False,
              do_clean: bool = False, only: Optional[str] = None) -> int:
    """构建一批技能。`root` 是仓根（含 `pyproject.toml` 与 `skill/`）。"""
    root = Path(root).resolve()
    dist = Path(dist) if dist else root.parent / ("%s-dist" % root.name)
    if do_clean:
        clean_dist(dist)
    version = read_version(root)
    rc = 0
    for spec in specs:
        if only and spec.name != only:
            continue
        if build_one(spec, version, meta, root, dist, do_zip) != 0:
            rc = 1
    return rc


def run_cli(specs: Sequence[SkillSpec], meta: ProjectMeta,
            root: Optional[Path] = None, dist: Optional[Path] = None,
            argv: Optional[Sequence[str]] = None) -> int:
    """各仓 `tools/build_skill.py` 的统一入口。"""
    root = Path(root) if root else Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description="打包技能包（两种归档形态）")
    ap.add_argument("--zip", action="store_true",
                    help="顺带打上传用的 ZIP（zip-root 形态）")
    ap.add_argument("--clean", action="store_true", help="先把旧产物挪到 _stale/")
    ap.add_argument("--name", default=None, help="只构建某个技能（缺省 = 全部）")
    args = ap.parse_args(argv)
    return build_all(specs, meta, root=root, dist=dist,
                     do_zip=args.zip, do_clean=args.clean, only=args.name)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """`python -m pasm_skills.build`：列出本库能力（基座仓自己没有技能包）。"""
    ap = argparse.ArgumentParser(
        prog="python -m pasm_skills.build",
        description="技能包打包库。基座仓不产出技能包；"
                    "请在各智能体仓的 tools/build_skill.py 里 import 本模块使用。")
    ap.parse_args(argv)
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
