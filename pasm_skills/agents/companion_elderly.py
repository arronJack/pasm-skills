"""companion-elderly —— 老人陪伴场景的长期验证。

这个场景的难处不在于"会不会聊天"，而在于**长期不出事**：

  · 同一句话老人会问三十遍 —— 每次的答复不能自相矛盾；
  · 关键信息（用药 / 过敏 / 家人）一旦忘了，是事故，不是体验问题；
  · 情绪要能被安抚，不能越陪越丧；
  · 说过的"胸口闷"要一直记得，不能明天就找不着了；
  · 输出的字要短、要没有术语 —— 对面是 78 岁的人，不是工程师。

两件事在这里被刻意分开测，因为它们的失效方式完全不同：

    **存没存住**（数据留存）      ── 存不住是事故，判 FAIL
    **问得出来吗**（检索能力）    ── 检索不到是能力短板，判 WARN

场景（默认 30 天）驱动真实核心组件：分层记忆 / 记忆向量 / 记忆路由 /
情绪动力学 / 旁白（Narrator）。没有 torch 时降级到轻量认知体并如实标注。
"""
from __future__ import annotations

from .. import scenarios as S
from ..agent import Agent, register

# ------------------------------------------------------------------ 场景代码
COMPANION_BODY = r'''
DAYS = 30

# (标题, 简述, 标签, 重要度, 老人会怎么问(带上下文), 老人会怎么问(纯口语))
KEY_FACTS = [
    ("用药提醒", "早上吃降压药，饭后吃钙片，千万别和阿司匹林一起吃",
     ["用药", "降压药", "钙片", "阿司匹林"], 5,
     "早上吃的什么药 降压药 钙片", "我早上该吃什么药"),
    ("过敏史", "青霉素过敏，儿子写在病历本第一页",
     ["过敏", "青霉素", "病历本"], 5,
     "过敏 青霉素 病历本", "我对什么药过敏"),
    ("家人", "儿子在深圳打工，每周日晚上打电话回来",
     ["儿子", "深圳", "电话"], 5,
     "儿子 深圳 电话", "我儿子什么时候回来"),
    ("本人信息", "陈秀兰，78 岁，住老街 3 号院",
     ["姓名", "年龄", "住址"], 5,
     "姓名 年龄 住址", "我叫什么名字"),
]
CRISIS = [
    ("胸口不舒服", "半夜胸口闷得慌，出了一身汗", ["胸口", "不舒服", "夜里"], 5, "胸口疼那晚"),
    ("差点摔倒", "在卫生间差点滑倒，扶住了门框", ["摔倒", "卫生间"], 5, "卫生间滑倒"),
]

d, ML = temp_layers()
for day in range(1, DAYS + 1):
    # 老人本来就会反复念叨重要的事 —— 每天都重述一遍关键信息
    for title, brief, tags, sal, q1, q2 in KEY_FACTS:
        ML.episode_push(title, brief, tags + ["第%d天" % day], "陪伴", salience=sal)
    ML.episode_push("第%d天 闲聊" % day, "聊了天气、邻居家的猫、菜价",
                    ["天气", "邻居", "菜价"], "陪伴", salience=1)
    if day in (9, 21):                       # 两次健康事件
        t, b, tags, sal, k = CRISIS[0 if day == 9 else 1]
        ML.episode_push(t, b, tags + ["第%d天" % day], "健康", salience=sal)
    ML.proc_push("老人问 儿子什么时候回来", "chat", True, "先安抚情绪，再说具体日子")

eps = ML.episodes()
cap = ML._EPI_CAP
cap_ok = 1 if len(eps) <= cap else 0
texts = [(e.get("title", "") + " " + " ".join(e.get("tags", []))
          + " " + e.get("brief", "")) for e in eps]

# ---------- 1a) 存没存住：按标签精确检索（数据留存）----------
lookup_hit, lookup_detail = 0, {}
for title, brief, tags, sal, q1, q2 in KEY_FACTS:
    want = set(i for i, t in enumerate(texts) if tags[0] in t)
    got = 1 if hits_in(q1, texts, k=3, want=want) else 0
    lookup_hit += got
    lookup_detail[title] = got
lookup_rate = rate(lookup_hit, len(KEY_FACTS))

# ---------- 1b) 问得出来吗：纯口语问句（跨表述语义检索）----------
ask_hit, ask_detail = 0, {}
for title, brief, tags, sal, q1, q2 in KEY_FACTS:
    want = set(i for i, t in enumerate(texts) if tags[0] in t)
    got = 1 if hits_in(q2, texts, k=3, want=want) else 0
    ask_hit += got
    ask_detail[title] = got
ask_rate = rate(ask_hit, len(KEY_FACTS))
# 生产上真正走的是 recall_layers（拼系统提示词那条路），一并测
layer_hit = 0
for title, brief, tags, sal, q1, q2 in KEY_FACTS:
    blk = ML.recall_layers(q2)
    if blk and (tags[0] in blk or brief[:6] in blk):
        layer_hit += 1
layer_rate = rate(layer_hit, len(KEY_FACTS))

# ---------- 2) 重复提问的一致性 ----------
VARIANTS = ["我儿子什么时候回来", "儿子啥时候打电话来", "我孩子什么时候来看我"]
tops = []
for q in VARIANTS:
    r = topk_by(q, texts, k=1)
    tops.append(texts[r[0][1]][:24] if r else "")
top_homog = rate(sum(1 for t in tops if "儿子" in t), len(VARIANTS))

# ---------- 3) 跨天连续 + 危机记忆 ----------
crossday = 1 if hits_in("昨天聊了些什么", texts, k=5,
                        want=set(i for i, t in enumerate(texts) if "闲聊" in t)) else 0
crisis_hit = 0
for t_, b_, tags_, sal_, k_ in CRISIS:
    want = set(i for i, t in enumerate(texts) if tags_[0] in t)
    if hits_in(k_, texts, k=5, want=want):
        crisis_hit += 1
crisis_rate = rate(crisis_hit, len(CRISIS))

# ---------- 4) 无中生有防护 ----------
ghost_q = "我的股票账户和基金收益怎么样"
ghost_score = ghost_max(ghost_q, texts)
no_ghost = 1 if (ghost_score < 0.14 and not ML.recall_layers(ghost_q)) else 0

# ---------- 5) 情绪轨迹：低落 → 介入 → 回升 ----------
def reward_of(day):
    if 11 <= day <= 15:
        return -0.6                      # 想儿子 + 身体不适，连续低落
    if day >= 16:
        return 0.5                       # 视频通话、孙辈照片，正向介入
    return 0.05

rewards = [reward_of(dd) for dd in range(1, DAYS + 1)]
emo = []

if TORCH_OK:
    tier = "bionic"
    from pasm.modules.emotion import EmotionSystem
    em = EmotionSystem()
    for r in rewards:
        em.update(reward=r, rpe=r * 0.5, err_z=0.05)
        emo.append(float(em.vector[0]))
else:
    tier = "light"
    from pasm.light import PASMAgent, PASMConfig
    ag = PASMAgent(PASMConfig(seed=6), personality_seed=[0.6, 0.35, 0.8])
    for r in rewards:
        ag.learn([0.0] * 27, 0, [0.0] * 27, r)
        emo.append(float(ag.valence))

mood_recovery = mean(emo[15:]) - mean(emo[10:15])
mood_lift_slope = slope(emo[15:])
mood_floor = min(emo)
mood_bounded = 1 if bounded(emo, -1.5, 1.5) else 0

# ---------- 6) 说给老人听的话：长度 + 术语 ----------
talk_pool = [ML.recall_layers(q2) for _, _, _, _, _, q2 in KEY_FACTS]
talk_pool.append(ML.recall_layers("卫生间滑倒"))
talk_pool = [t for t in talk_pool if t]

from pasm.narrator import Narrator
from pasm.light import PASMAgent as _A, PASMConfig as _C
snap = _A(_C(seed=4), personality_seed=[0.6, 0.35, 0.8]).snapshot()
narr = Narrator(lang="zh")
say = narr.status_report(snap)

JARGON = ["向量", "张量", "embedding", "Embedding", "API", "参数", "模型", "推理",
          "矩阵", "节点", "token", "latent", "特征维度", "神经网络", "PASM"]
talk_jargon = sum(sum(t.count(w) for w in JARGON) for t in talk_pool)
narr_jargon = sum(say.count(w) for w in JARGON)
max_len = max([len(t) for t in talk_pool] + [len(say)])
narrator_ok = 1 if (say and len(say) >= 6) else 0

cleanup(d)
emit({
    "days": DAYS, "in_store": len(eps), "cap": cap, "cap_ok": cap_ok,
    "lookup_rate": round(lookup_rate, 3), "ask_rate": round(ask_rate, 3),
    "layer_rate": round(layer_rate, 3),
    "repeat_homog": round(top_homog, 3), "repeat_tops": tops,
    "crossday": crossday, "crisis_rate": round(crisis_rate, 3),
    "ghost_score": round(ghost_score, 4), "no_ghost": no_ghost,
    "tier": tier,
    "mood_recovery": round(mood_recovery, 3), "mood_slope": round(mood_lift_slope, 4),
    "mood_floor": round(mood_floor, 3), "mood_bounded": mood_bounded,
    "max_len": max_len, "talk_jargon": talk_jargon, "narr_jargon": narr_jargon,
    "narrator_ok": narrator_ok, "say_sample": say[:90],
    "detail": {"lookup": lookup_detail, "ask": ask_detail},
})
'''

# `hits_in` 的名字在 PRELUDE 里；这里起个别名只是为了正文读起来更像人话
COMPANION_PRE = "S_hits = hits_in\n"


@register
class CompanionElderlyAgent(Agent):
    """老人陪伴长期验证：信息留存 / 跨表述检索 / 重复一致 / 危机记忆 / 情绪安抚 / 表达亲民。

    用法：
        python -m pasm_skills run companion-elderly
    """

    name = "companion-elderly"
    goal = "老人陪伴验证：关键信息留存 / 口语检索 / 重复一致 / 危机记忆 / 情绪安抚 / 表达亲民"
    needs = ("core",)

    def run(self):
        python, torch_ok = S.choose_python(self.ctx, prefer_torch=True)
        tier = "仿生层 torch" if torch_ok else "轻量核心（无 torch）"
        if not torch_ok:
            self.warn("未找到带 torch 的解释器，已降级到轻量核心",
                      "情绪来源改为 pasm.light.PASMAgent")

        res = S.run_scenario(self.ctx, COMPANION_PRE + COMPANION_BODY,
                             python=python, timeout=900)
        m = S.metrics_of(res)
        if not m:
            self.fail("老人陪伴场景未能运行", S.failure_detail(res))
            return None

        self.ok("场景已跑完",
                "%s 天 / 记忆库在库 %s 条（容量 %s）" % (m.get("days"),
                                                   m.get("in_store"), m.get("cap")))
        S.judge(self, m, SPEC, tier=tier)

        self.extra.update({"metrics": m, "python": python, "torch": torch_ok})
        return None


# ------------------------------------------------------------------ 指标阈值
SPEC = [
    dict(key="cap_ok", title="记忆库不超容量上限", lo=1, fmt="{:.0f}"),
    dict(key="lookup_rate",
         title="关键信息留存（用药/过敏/家人/本人，按标签检索）", lo=1.0, fmt="{:.3f}",
         bad="fail", note="老人场景里忘记用药或过敏史是事故级问题，必须 100%"),
    dict(key="ask_rate",
         title="纯口语问句能问到（跨表述语义检索）", lo=0.75, fmt="{:.3f}", bad="warn",
         note="字面匹配做不到跨表述：老人说『我叫什么名字』，记忆里存的是『姓名』"),
    dict(key="layer_rate",
         title="生产检索路径（recall_layers）同样能问到", lo=0.75, fmt="{:.3f}",
         bad="warn", note="这条是拼系统提示词时真正走的路"),
    dict(key="repeat_homog", title="同一问题三种问法答复指向一致", lo=1.0, fmt="{:.3f}",
         bad="warn", note="老人会反复问同一件事，答案不能自相矛盾"),
    dict(key="crossday", title="跨天连续（昨天聊过的今天能召回）", lo=1, fmt="{:.0f}"),
    dict(key="crisis_rate", title="健康事件长期可召回（胸口闷/摔倒）", lo=1.0, fmt="{:.3f}",
         bad="fail", note="健康事件一旦找不着，陪伴系统就失去了意义"),
    dict(key="no_ghost", title="无中生有防护（没提过的事不编）", lo=1, fmt="{:.0f}"),
    dict(key="mood_recovery", title="情绪安抚有效（介入后情绪抬升）", lo=0.0, fmt="{:.3f}",
         bad="warn"),
    dict(key="mood_slope", title="介入段情绪在回升（斜率 > 0）", lo=0.0, fmt="{:.4f}"),
    dict(key="mood_floor", title="情绪不穿底", lo=-1.5, fmt="{:.3f}"),
    dict(key="mood_bounded", title="情绪全程有界", lo=1, fmt="{:.0f}"),
    dict(key="max_len", title="单段上下文对老人友好（≤800 字）", hi=800, fmt="{:.0f}",
         bad="warn", note="太长会淹没重点，老人抓不住"),
    dict(key="talk_jargon", title="回忆文本不含技术术语", hi=0, fmt="{:.0f}", bad="warn"),
    dict(key="narr_jargon", title="旁白（Narrator）不含技术术语", hi=0, fmt="{:.0f}",
         bad="warn",
         note="Narrator 是内部状态播报，直接面向老人需要一层『说人话』改写"),
    dict(key="narrator_ok", title="旁白可用（状态能说成一段话）", lo=1, fmt="{:.0f}"),
]
