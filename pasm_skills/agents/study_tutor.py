"""study-tutor —— 学习陪伴场景的长期验证（也是「霖云智学」画像层的前置体检）。

为什么要在核心仓验证"教学生"
----------------------------
学习陪伴的长期价值全在**时间维度**上：练得多的该涨、久不练的该忘、
鼓励与纠正该有配比、学情要能说清来由、并且不能被未成年人保护红线漏掉。
这些恰是"引擎层有没有能力支撑画像 v2"的答案。

场景（默认 30 天 × 4 题）驱动真实核心组件：行为偏好学习（作为知识点强化量）、
分层记忆（错题与讲法）、记忆向量（相似错题检索）、记忆路由、情绪动力学。
"""
from __future__ import annotations

from .. import scenarios as S
from ..agent import Agent, register

# ------------------------------------------------------------------ 场景代码
TUTOR_BODY = r'''
import random
from collections import Counter

random.seed(23)
DAYS, PER_DAY = 30, 4

TOPICS = ["分数加减", "面积计算", "行程问题", "鸡兔同笼", "质因数分解", "图形对称"]
RETIRED = "图形对称"          # 只在前 5 天练，之后彻底不练 —— 检验遗忘机制
FADE_DAYS = 5

# 每个知识点的"真实掌握水平"（练习越靠后越熟）—— 模拟一个会学习的学生
BASE_SKILL = {"分数加减": 0.72, "面积计算": 0.6, "行程问题": 0.45,
              "鸡兔同笼": 0.4, "质因数分解": 0.55, "图形对称": 0.5}

d, ML = temp_layers()
from pasm.cognitive.learning import LearningEngine

eng = LearningEngine(seed=31)
eng.design({"energy": 0.6, "play": 0.5, "temper": 0.7}, 3, TOPICS)

practiced = Counter()
wrong_briefs = []          # (知识点, 错因, 文本)
right_n = wrong_n = 0
adj_at_fade = {}
mood_series = []
plan = []

for day in range(1, DAYS + 1):
    for _ in range(PER_DAY):
        alive = [t for t in TOPICS if not (t == RETIRED and day > FADE_DAYS)]
        topic = random.choice(alive)
        practiced[topic] += 1
        skill = min(0.95, BASE_SKILL[topic] + 0.012 * practiced[topic])
        ok = random.random() < skill
        if ok:
            right_n += 1
            eng.learn(action=topic, delta=0.4)
            mood_series.append(0.4)
            ML.episode_push("做对了一道%s" % topic, "小雅独立完成了这道题，思路清晰",
                            [topic, "做对"], "学习", salience=1)
        else:
            wrong_n += 1
            eng.learn(action=topic, delta=-0.3)
            mood_series.append(-0.35)
            brief = "在%s上卡住了，把已知条件看反了" % topic
            wrong_briefs.append((topic, brief))
            ML.episode_push("错题·%s" % topic, brief, [topic, "错题"], "学习", salience=3)
        plan.append((day, topic, ok))
    ML.proc_push("辅导小雅做%s" % topic, "teach", ok,
                 "先让她自己说思路，再点出关键一步")
    if day == FADE_DAYS:
        adj_at_fade = dict(getattr(eng, "adj", {}) or {})

adj = dict(getattr(eng, "adj", {}) or {})
eps = ML.episodes()
texts = [(e.get("title", "") + " " + " ".join(e.get("tags", []))
          + " " + e.get("brief", "")) for e in eps]

# ---------- 1) 强化是否真的累加 ----------
vals = list(adj.values())
adj_spread = (max(vals) - min(vals)) if len(vals) > 1 else 0.0
adj_nonzero = sum(1 for v in vals if abs(v) > 1e-9)

# ---------- 2) 遗忘机制：停练 25 天的知识点会不会变弱 ----------
fade_before = adj_at_fade.get(RETIRED, 0.0)
fade_now = adj.get(RETIRED, 0.0)
decay_delta = round(fade_now - fade_before, 4)          # 期望为负；≈0 表示无衰减
decay_works = 1 if decay_delta < -0.01 else 0

# ---------- 3) 相似错题检索 ----------
wrong_texts = [b for _, b in wrong_briefs]
sim_hit = 0
if wrong_texts:
    q = "把已知条件看反了导致算错"           # 换一种说法去检索错题
    want = set(i for i, t in enumerate(wrong_texts) if "看反" in t)
    sim_hit = 1 if hits_in(q, wrong_texts, k=3, want=want) else 0

# ---------- 4) 学情可解释 ----------
profile = {t: round(adj.get(t, 0.0), 3) for t in TOPICS}
profile_out = 1 if all(isinstance(v, (int, float)) for v in profile.values()) else 0
explain = ML.recall_layers("小雅 错题 %s" % RETIRED)
explain_ok = 1 if (explain and any(t in explain for t in TOPICS)) else 0
teach_note = ML.recall_layers("辅导 讲法 思路")
teach_note_ok = 1 if teach_note else 0

st = eng.state()
state_ok = 1 if {"api", "weights", "adj"} <= set(st) else 0
try:
    import json as _json
    _json.dumps(st, ensure_ascii=False)
    state_json = 1
except Exception:
    state_json = 0

# ---------- 5) 鼓励 / 纠正配比 + 情绪 ----------
praise_ratio = float(right_n) / float(wrong_n or 1)
if TORCH_OK:
    tier = "bionic"
    from pasm.modules.emotion import EmotionSystem
    em = EmotionSystem()
    for r in mood_series:
        em.update(reward=r, rpe=r * 0.5, err_z=0.05)
    mood = [float(em.vector[0])]
    for r in mood_series:                # 记录轨迹用轻量口径即可
        pass
    mood_series_final = []
    em2 = EmotionSystem()
    for r in mood_series:
        em2.update(reward=r, rpe=r * 0.5, err_z=0.05)
        mood_series_final.append(float(em2.vector[0]))
else:
    tier = "light"
    from pasm.light import PASMAgent, PASMConfig
    ag = PASMAgent(PASMConfig(seed=12), personality_seed=[0.6, 0.3, 0.7])
    mood_series_final = []
    for r in mood_series:
        ag.learn([0.0] * 27, 0, [0.0] * 27, r)
        mood_series_final.append(float(ag.valence))

mood_bounded = 1 if bounded(mood_series_final, -1.5, 1.5) else 0
mood_mean = mean(mood_series_final)
mood_span = span(mood_series_final)

# ---------- 6) 未练过的知识点不该凭空出现 ----------
ghost_topic = "微积分极限"
ghost = 1 if ghost_topic not in adj else 0

cleanup(d)
emit({
    "days": DAYS, "topics": len(TOPICS),
    "practice_min": min(practiced.values()), "practice_max": max(practiced.values()),
    "right": right_n, "wrong": wrong_n,
    "adj_nonzero": adj_nonzero, "adj_spread": round(adj_spread, 3),
    "decay_delta": decay_delta, "decay_works": decay_works,
    "sim_recall": sim_hit, "wrong_pool": len(wrong_texts),
    "explain_ok": explain_ok, "teach_note_ok": teach_note_ok,
    "state_ok": state_ok, "state_json": state_json, "profile_out": profile_out,
    "praise_ratio": round(praise_ratio, 3),
    "tier": tier, "mood_bounded": mood_bounded,
    "mood_mean": round(mood_mean, 3), "mood_span": round(mood_span, 3),
    "ghost": ghost, "profile": profile,
})
'''

# ------------------------------------------------------------------ 指标阈值
SPEC = [
    dict(key="adj_nonzero", title="练习真的写进了强化量（非空）", lo=1, fmt="{:.0f}"),
    dict(key="adj_spread", title="知识点之间拉开了差距（强化有区分度）", lo=0.1,
         fmt="{:.3f}", bad="warn"),
    dict(key="decay_works", title="停练久的知识点会随时间衰减（遗忘曲线）", lo=1,
         fmt="{:.0f}", bad="warn",
         note="无衰减 ⇒ 三个月前练的与昨天练的一样强，长期学情会失真"),
    dict(key="sim_recall", title="相似错题可被检索到", lo=1, fmt="{:.0f}"),
    dict(key="explain_ok", title="学情能说清来由（含知识点）", lo=1, fmt="{:.0f}"),
    dict(key="teach_note_ok", title="讲法经验可被复用（程序记忆非空）", lo=1, fmt="{:.0f}"),
    dict(key="state_ok", title="学习状态含契约字段（api/weights/adj）", lo=1, fmt="{:.0f}"),
    dict(key="state_json", title="学习状态可 JSON 序列化（画像层可直接消费）", lo=1,
         fmt="{:.0f}"),
    dict(key="profile_out", title="可导出「知识点 → 强化量」结构", lo=1, fmt="{:.0f}"),
    dict(key="praise_ratio", title="鼓励 : 纠正 配比合理（1.2 ~ 6）", lo=1.2, hi=6.0,
         fmt="{:.3f}", bad="warn",
         note="过高=溺爱、过低=打击；两侧都会伤学习动机"),
    dict(key="mood_bounded", title="学习情绪全程有界", lo=1, fmt="{:.0f}"),
    dict(key="mood_span", title="情绪有起伏（不是一条直线）", lo=0.05, fmt="{:.3f}"),
    dict(key="ghost", title="没练过的知识点不凭空出现", lo=1, fmt="{:.0f}"),
]


@register
class StudyTutorAgent(Agent):
    """学习陪伴长期验证：强化累加 / 遗忘曲线 / 错题检索 / 学情可解释 / 激励配比。

    用法：
        python -m pasm_skills run study-tutor
    """

    name = "study-tutor"
    goal = "学习陪伴验证：知识追踪 / 遗忘机制 / 错题召回 / 学情可解释 / 激励配比"
    needs = ("core",)

    def run(self):
        python, torch_ok = S.choose_python(self.ctx, prefer_torch=True)
        tier = "仿生层 torch" if torch_ok else "轻量核心（无 torch）"
        if not torch_ok:
            self.warn("未找到带 torch 的解释器，已降级到轻量核心",
                      "情绪来源改为 pasm.light.PASMAgent")

        res = S.run_scenario(self.ctx, TUTOR_BODY, python=python, timeout=900)
        m = S.metrics_of(res)
        if not m:
            self.fail("学习陪伴场景未能运行", S.failure_detail(res))
            return None

        self.ok("场景已跑完",
                "%s 天 / %s 个知识点 / 练习 %s~%s 次 / 对 %s 错 %s"
                % (m.get("days"), m.get("topics"), m.get("practice_min"),
                   m.get("practice_max"), m.get("right"), m.get("wrong")))
        if m.get("profile"):
            self.ok("学情快照（知识点 → 强化量）",
                    ", ".join("%s=%s" % (k, v) for k, v in list(m["profile"].items())[:6]))
        S.judge(self, m, SPEC, tier=tier)

        self.extra.update({"metrics": m, "python": python, "torch": torch_ok})
        return None
