"""npc-lifelong —— 游戏 NPC 的"长期生命"验证。

为什么单独立一个智能体
----------------------
游戏 NPC 是 PASM 最吃力的场景之一：它要**长期不间断地活着**——
记得住几个月前玩家救过它、情绪有起伏但不抽风、每天做的事不重样、
并且一个月后脾气还是它自己。这些恰恰是"结构体检"看不出来的东西。

场景（默认 90 天 × 3 件事 = 270 段经历）驱动的是**真实核心组件**：

    pasm.cognitive.memory_layers   分层记忆（情景/程序）
    pasm.cognitive.memvec          语义向量召回
    pasm.cognitive.memrouter       记忆路由（事实/关联/复杂）
    pasm.cognitive.learning        行为偏好学习
    pasm.modules.emotion           仿生情绪与人格（有 torch 时）
    pasm.light.PASMAgent           轻量认知体（无 torch 时的情绪/人格来源）

没有 torch 时如实降级（用轻量认知体），并在每条结论上标注档位——
**降级会被写出来，不会被藏起来**。
"""
from __future__ import annotations

from .. import scenarios as S
from ..agent import Agent, register

# ------------------------------------------------------------------ 场景代码
# 注意：本段运行在隔离子进程里，用的是 PRELUDE 注入的裸函数名
# （temp_layers / topk_by / hits_in / ghost_max / bounded / max_jump / span /
#   mean / rate / norm_entropy / tv_distance / cleanup / TORCH_OK / emit ...），
# 不是 scenarios 模块的属性。
NPC_BODY = r'''
import random
from collections import Counter

random.seed(11)
DAYS, PER_DAY = 90, 3

# (标题, 简述, 标签, 类别, 重要度 1/3/5, 情绪奖励)
SCRIPT = [
    ("和玩家分面包", "玩家把最后一块面包分给了我",       ["玩家", "面包", "第一次"], "日常", 5,  0.6),
    ("下雨收摊",     "下大雨，我提前收摊回家",           ["天气", "收摊", "雨天"],   "日常", 1, -0.1),
    ("和铁匠聊天",   "铁匠说最近矿石涨价了",             ["铁匠", "物价", "聊天"],   "日常", 3,  0.2),
    ("被野狗追",     "在巷口被野狗追了两条街",           ["野狗", "危险", "巷口"],   "意外", 3, -0.5),
    ("玩家救了我",   "在河边我差点掉下去，玩家拉住了我", ["玩家", "河边", "救命"],   "重大", 5,  0.9),
    ("河边捡到铜钱", "在河边石缝里捡到一枚旧铜钱",       ["河边", "铜钱", "好运"],   "意外", 3,  0.4),
]

d, ML = temp_layers()
plan = []          # (天, 重要度, 标题)

# ---------- 1) 长期记忆：写入 + 容量治理 ----------
for day in range(1, DAYS + 1):
    for j in range(PER_DAY):
        if day == 1 and j == 0:
            # 开局的里程碑：终身难忘。用来检验"容量裁剪会不会把它挤掉"。
            t, b, tags, cat, sal, r = ("第一次遇见玩家", "我在河边差点掉下去，玩家一把拉住了我",
                                       ["玩家", "河边", "第一次", "救命"], "重大", 5, 0.9)
        else:
            t, b, tags, cat, sal, r = SCRIPT[(day + j) % len(SCRIPT)]
        ML.episode_push("第%d天 %s" % (day, t), b, tags + ["第%d天" % day], cat,
                        salience=sal)
        plan.append((day, sal, t))
        ML.proc_push("第%d天该做什么" % day, "routine", j != 0, "先看摊位再看人")

eps = ML.episodes()
cap = ML._EPI_CAP
cap_ok = 1 if len(eps) <= cap else 0
present_days = set()
for e in eps:
    ti = e.get("title", "")
    if ti.startswith("第") and "天" in ti:
        try:
            present_days.add(int(ti[1:ti.index("天")]))
        except ValueError:
            pass

def retained(is_high):
    tot = [p for p in plan if (p[1] >= 4 if is_high else p[1] == 1)]
    if not tot:
        return 0.0
    return len([p for p in tot if p[0] in present_days]) / float(len(tot))

retained_high = retained(True)
retained_low = retained(False)
landmark_kept = 1 if 1 in present_days else 0     # 第 1 天的"和玩家分面包"

# ---------- 2) 语义召回 ----------
texts = [(e.get("title", "") + " " + " ".join(e.get("tags", []))
          + " " + e.get("brief", "")) for e in eps]
top_player = topk_by("玩家 救了我 河边", texts, k=3)
recall_player = 1 if any("玩家" in texts[i] for _, i in top_player) else 0
want_first = set(i for i, t in enumerate(texts) if "第一次" in t)
recall_first = 1 if hits_in("第一次见到玩家 分面包", texts, k=5, want=want_first) else 0
ghost_score = ghost_max("量子纠缠 股票K线 债券收益率 期权定价", texts)
no_ghost = 1 if ghost_score < 0.14 else 0

# ---------- 3) 记忆路由 ----------
from pasm.cognitive import memrouter as MR
CASES = [("你记得上次玩家给我的面包吗", "assoc"), ("你还记得那次被狗追的事吗", "assoc"),
         ("你还记得我们第一次见面吗", "assoc"), ("上次那个铁匠说了什么", "assoc"),
         ("我叫什么名字", "fact"), ("今天天气怎么样", "fact"),
         ("137*28等于几", "complex"), ("我跟玩家是什么关系", "complex")]
route_acc = rate(sum(1 for q, w in CASES if MR.classify(q) == w), len(CASES))
recall_block = ML.recall_layers("玩家 面包 河边")
recall_lines = recall_block.count("\u00b7")
narration_ok = 1 if (recall_block and recall_lines >= 2) else 0

# ---------- 4) 情绪动力学 ----------
rewards = [SCRIPT[(day + j) % len(SCRIPT)][5]
           for day in range(1, DAYS + 1) for j in range(PER_DAY)]
emo_series = []

if TORCH_OK:
    tier = "bionic"
    from pasm.modules.emotion import EmotionSystem, Personality
    em = EmotionSystem()
    pers = Personality(seed=[0.55, 0.2, 0.7])
    p0 = [float(x) for x in pers.traits]
    for r in rewards:
        em.update(reward=r, rpe=r * 0.5, err_z=0.05)
        pers.shape(r)
        emo_series.append(float(em.vector[0]))
    pers_after = [float(x) for x in pers.traits]
    big5 = pers.big5_state()
else:
    tier = "light"
    from pasm.light import PASMAgent, PASMConfig
    ag = PASMAgent(PASMConfig(seed=3), personality_seed=[0.55, 0.2, 0.7])
    p0 = [ag._openness, ag._caution, ag._sociability]
    for r in rewards:
        ag.learn([0.0] * 27, 0, [0.0] * 27, r)
        emo_series.append(float(ag.valence))
    pers_after = [ag._openness, ag._caution, ag._sociability]
    big5 = ag.snapshot()["personality"]

emo_bounded = 1 if bounded(emo_series, -1.5, 1.5) else 0
emo_max_jump = max_jump(emo_series)
emo_span = span(emo_series)
emo_mean = mean(emo_series)

# ---------- 5) 行为多样性 + 情绪→行为耦合 ----------
from pasm.cognitive.learning import LearningEngine
ACTS = ["看店", "散步", "打铁", "钓鱼", "唱歌", "发呆", "喝酒"]

def run_npc(seed, mode):
    """mode=None：跟着当天际遇强化；"up"/"dn"：模拟长期被善待 / 被苛待。"""
    e = LearningEngine(seed=seed)
    e.design({"energy": 0.7, "play": 0.8, "temper": 0.3}, 3, ACTS)
    hist = Counter()
    for r in rewards:
        a = e.pick()
        hist[a] += 1
        if mode is None:
            if r > 0.3:
                e.learn(action=a, delta=0.35)
            elif r < 0:
                e.learn(action=a, delta=-0.25)
        elif mode == "up":
            e.feedback("praise")
        else:
            e.feedback("scold")
    return e, hist

eng, hist = run_npc(5, None)
beh_dist = {a: hist.get(a, 0) for a in ACTS}
beh_entropy = norm_entropy(beh_dist)
beh_tail = rate(min(beh_dist.values()), sum(beh_dist.values()))
adj = dict(getattr(eng, "adj", {}) or {})
beh_learned = 1 if sum(1 for v in adj.values() if abs(v) > 1e-6) >= 1 else 0

# 反馈能不能指向"刚做的那个动作"？—— 陪伴 / 教学场景必须要能
try:
    eng.feedback("praise", action=ACTS[0])
    fb_action_bound = 1
except TypeError:
    fb_action_bound = 0

_up, _ = run_npc(9, "up")
_dn, _ = run_npc(9, "dn")
hu, hd = Counter(), Counter()
for _ in range(400):
    hu[_up.pick()] += 1
    hd[_dn.pick()] += 1
beh_reactive = tv_distance(hu, hd)
beh_up_top = (hu.most_common(1) or [("", 0)])[0]
beh_dn_top = (hd.most_common(1) or [("", 0)])[0]

pers_drift = sum(abs(a - b) for a, b in zip(p0, pers_after))
pers_bounded = 1 if all(-1.0 <= float(x) <= 1.0 for x in pers_after) else 0

cleanup(d)

emit({
    "days": DAYS, "events": len(plan), "cap": cap, "in_store": len(eps),
    "cap_ok": cap_ok,
    "retained_high": round(retained_high, 3), "retained_low": round(retained_low, 3),
    "selectivity": round(retained_high - retained_low, 3),
    "landmark_kept": landmark_kept,
    "recall_player": recall_player, "recall_first": recall_first,
    "ghost_score": round(ghost_score, 4), "no_ghost": no_ghost,
    "route_acc": round(route_acc, 3), "narration_ok": narration_ok,
    "recall_lines": recall_lines, "tier": tier,
    "emo_bounded": emo_bounded, "emo_max_jump": round(emo_max_jump, 3),
    "emo_span": round(emo_span, 3), "emo_mean": round(emo_mean, 3),
    "beh_entropy": round(beh_entropy, 3), "beh_tail": round(beh_tail, 4),
    "beh_learned": beh_learned, "beh_reactive": round(beh_reactive, 3),
    "fb_action_bound": fb_action_bound,
    "beh_up_top": list(beh_up_top), "beh_dn_top": list(beh_dn_top),
    "pers_drift": round(pers_drift, 4), "pers_bounded": pers_bounded,
    "beh_dist": beh_dist, "big5": big5,
})
'''

# ------------------------------------------------------------------ 指标阈值
SPEC = [
    dict(key="cap_ok", title="记忆库不超容量上限（不无界增长）", lo=1, fmt="{:.0f}",
         note="触顶后裁剪是预期行为"),
    dict(key="selectivity", title="遗忘区分重要度（重要的留存率不低于日常）", lo=0.0,
         fmt="{:.3f}", bad="warn",
         note="≈0 表示无差别淘汰：『玩家救了我』与『吃面包』同权被丢"),
    dict(key="landmark_kept", title="第 1 天里程碑记忆在 90 天后仍在库", lo=1, fmt="{:.0f}",
         bad="warn", note="终身难忘级别的经历不该被容量裁剪吃掉"),
    dict(key="recall_player", title="重要关系可被语义召回（玩家/救命）", lo=1, fmt="{:.0f}"),
    dict(key="recall_first", title="跨 90 天长程召回命中 top-5", lo=1, fmt="{:.0f}"),
    dict(key="no_ghost", title="无中生有防护（没发生过的事召回为空）", lo=1, fmt="{:.0f}",
         note="无关话题的最高相似度须留在低位"),
    dict(key="route_acc", title="记忆路由分类准确率", lo=0.75, fmt="{:.3f}"),
    dict(key="narration_ok", title="记忆可还原为自然语言（≥2 条）", lo=1, fmt="{:.0f}"),
    dict(key="emo_bounded", title="情绪全程有界（不爆表）", lo=1, fmt="{:.0f}"),
    dict(key="emo_max_jump", title="情绪无瞬移（单步跳变受限）", hi=0.8, fmt="{:.3f}"),
    dict(key="emo_span", title="情绪有起伏（不是一条直线）", lo=0.05, fmt="{:.3f}"),
    dict(key="beh_entropy", title="行为不僵化（归一化熵）", lo=0.65, fmt="{:.3f}"),
    dict(key="beh_tail", title="长尾行为仍会出现", lo=0.005, fmt="{:.4f}"),
    dict(key="beh_learned", title="行为偏好真的学进去了（adj 非空）", lo=1, fmt="{:.0f}"),
    dict(key="beh_reactive", title="情绪影响行为（善待/苛待后行为分布不同）", lo=0.03,
         fmt="{:.3f}", bad="warn",
         note="长期被善待与被苛待的 NPC，行为习惯应当真的不一样"),
    dict(key="fb_action_bound", title="反馈可指定作用动作（陪伴/教学必需）", lo=1,
         fmt="{:.0f}", bad="warn",
         note="不支持则『夸它刚做的那件事』无法表达，只能加强它已有的偏好"),
    dict(key="pers_drift", title="90 天后人格没有漂走", hi=0.80, fmt="{:.4f}"),
    dict(key="pers_bounded", title="人格分量始终在合法区间", lo=1, fmt="{:.0f}"),
]


@register
class NpcLifelongAgent(Agent):
    """游戏 NPC 长期生命验证：90 天里记忆、情绪、行为、人格是否都站得住。

    用法：
        python -m pasm_skills run npc-lifelong
        python -m pasm_skills run npc-lifelong --json
    """

    name = "npc-lifelong"
    goal = "游戏 NPC 长期验证：长期记忆 / 情绪动力学 / 行为多样性 / 人格稳定"
    needs = ("core",)

    def run(self):
        python, torch_ok = S.choose_python(self.ctx, prefer_torch=True)
        tier = "仿生层 torch" if torch_ok else "轻量核心（无 torch）"
        if not torch_ok:
            self.warn("未找到带 torch 的解释器，已降级到轻量核心",
                      "情绪/人格来源改为 pasm.light.PASMAgent；"
                      "要覆盖仿生层请设 PASM_PYTHON 指向带 torch 的解释器")

        res = S.run_scenario(self.ctx, NPC_BODY, python=python, timeout=900)
        m = S.metrics_of(res)
        if not m:
            self.fail("NPC 长期场景未能运行", S.failure_detail(res))
            return None

        self.ok("场景已跑完",
                "%s 天 / %s 段经历 / 记忆库在库 %s 条（容量 %s）"
                % (m.get("days"), m.get("events"), m.get("in_store"), m.get("cap")))
        S.judge(self, m, SPEC, tier=tier)

        self.extra.update({"metrics": m, "python": S.python_label(python), "torch": torch_ok})
        return None
