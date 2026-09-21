# -*- coding: utf-8 -*-
"""反例对照：故意把 ``capabilities.py`` 改坏，确认自检**真的抓得住**。

为什么要留这个脚本
------------------
`capabilities.selftest()` 报 19 项全绿，本身**不能说明断言是有效的** ——
断言可能写空了、或者恒真。2026-09-21 实测就抓到过一条：原先的隔离断言写成
"两边互不包含"，结果注册表整个坏掉、两边都返回空列表时**照样通过**（假绿）。
改成"各自必须看到自己的 + 看不到对方的"之后才真正可证伪。

所以：**任何"全绿"都要配一次"故意造错"**。跑这个脚本，三处反例必须都被抓住，
跑完无条件还原。

用法::

    python tools/falsify_capabilities.py
    # 退出码 0 = 全部反例被抓住且已还原；非 0 = 有断言抓不住（回去补断言）
"""
import io
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SRC = REPO / "pasm_skills" / "cognition" / "capabilities.py"
ENV = dict(os.environ, PYTHONPATH=str(REPO))

#: (要验的断言名, 原文锚点, 改坏后的文本)
#: 改坏方式要**刁钻** —— "让函数直接崩"会被退出码顺带抓到，
#: 只有"代码照跑但行为错"才真正考验断言。
CASES = [
    ("按 agent_id 隔离：各自只看到自己的记忆",
     "        if agent_id not in self._agents:\n            p = dict(self._default_persona)",
     "        if True:\n"
     "            agent_id = \"__shared__\"\n"
     "            p = dict(self._default_persona)\n"
     "            if agent_id in self._agents:\n"
     "                return self._agents[agent_id]"),
    ("空 query 抛 ValueError",
     '        if not query:\n            raise ValueError("query 不能为空")',
     '        if False:\n            raise ValueError("query 不能为空")'),
    ("重启后人格可恢复",
     "            saved = None if persona else self._saved_persona(agent_id)",
     "            saved = None"),
]


def run():
    p = subprocess.run([sys.executable, "-m", "pasm_skills.cognition.capabilities"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=ENV, cwd=str(REPO))
    return (p.stdout or "") + (p.stderr or ""), p.returncode


def main() -> int:
    base = io.open(SRC, encoding="utf-8", newline="").read()

    out, rc = run()
    if rc != 0 or "0 项失败" not in out:
        print("[中止] 基线不是全绿，先修好再谈反例。rc=%s" % rc)
        print(out[-500:])
        return 2
    print("[基线] 全绿 ✓\n")

    bad = 0
    try:
        for name, old, new in CASES:
            if old not in base:
                print("[跳过] 锚点没命中（代码改过？）: %s" % name)
                bad += 1
                continue
            io.open(SRC, "w", encoding="utf-8", newline="").write(
                base.replace(old, new, 1))
            out2, rc2 = run()
            caught = (rc2 != 0) and (name.split("：")[0] in out2)
            print("%s %s  -> rc=%s 被抓=%s"
                  % ("[PASS]" if caught else "[FAIL]", name, rc2, caught))
            if not caught:
                bad += 1
    finally:
        io.open(SRC, "w", encoding="utf-8", newline="").write(base)

    out3, rc3 = run()
    restored = (rc3 == 0) and ("0 项失败" in out3)
    print("\n[还原] 回到全绿=%s" % restored)
    if not restored:
        print(out3[-500:])
        bad += 1

    print("\n结论：%s" % ("全部反例都被抓住 ✓" if bad == 0 else "%d 处没抓住 ✗" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
