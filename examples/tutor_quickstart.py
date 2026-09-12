"""学习陪伴演示 —— 看到薄弱点定位 + 自适应选题：

    cd pasm-skills && python -m pasm_agents demo tutor
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pasm_agents import LearningTutor  # noqa: E402


def main():
    t = LearningTutor(agent_id="example_xiaoya", persona={
        "name": "小雅", "grade": "五年级",
        "tone": "温柔、耐心",
    })

    print(f"[init] {t!r}  tier={t.tier}")
    print()

    # 模拟 5 次作答：分数加减很差，其它还行
    t.report("分数加减", 0.4)
    t.report("分数加减", 0.5)
    t.report("面积计算", 0.9)
    t.report("鸡兔同笼", 0.7)
    t.report("行程问题", 0.85)

    print(f"[state] 知识点掌握度: {t.state.notes['knowledge_state']}")
    print(f"[pick_next] 最弱 → {t.pick_next()}")
    print(f"[chat 难]    → {t.chat('分数加减好难')}")
    print(f"[chat 哪里差] → {t.chat('我哪里不行')}")

    t.save()
    print(f"\n[saved] {t.persist_dir}")


if __name__ == "__main__":
    main()