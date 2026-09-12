"""soak-longrun —— 长效耐久（长期验证里最容易被忽略、也最致命的一块）。

前三个领域智能体查的是"**行为对不对**"；这个查的是"**跑久了会不会垮**"：

  · 单步耗时会不会越跑越慢（隐性 O(n²) / 内存泄漏）；
  · 记忆库会不会无界膨胀；
  · 存档 → 读档能不能一字不差地回到原状；
  · 人格会不会被推到边界钉死（0 或 1，再也回不来）；
  · 行为会不会在几万步后慢慢退化成"永远做同一件事"。

这些症状在短测里全都看不见，只有把步数拉长才会露头 —— 而真实部署里
NPC / 陪伴体是要连续跑几个月的。

**为什么轻量认知体是必测项**：安装包（无 torch）跑的就是 `pasm.light.PASMAgent`，
它才是用户机器上真实运行的那条路径。所以即使本机装了 torch，轻量档也照测不误。
"""
from __future__ import annotations

from .. import scenarios as S
from ..agent import Agent, register

# ------------------------------------------------------------------ 场景代码
SOAK_BODY = r'''
import json, os, tracemalloc
from collections import Counter

STEPS = 6000
PICK_STEPS = 6000
EPI_WARM, EPI_FLOOD = 400, 1600

d, ML = temp_layers()
ACTS = ["看店", "散步", "打铁", "钓鱼", "唱歌", "发呆", "喝酒"]

def rew(i):
    """长期相处：多数日子平淡，偶尔好事，偶尔坏事。"""
    if i % 11 == 0:
        return 0.8
    if i % 7 == 0:
        return -0.4
    return 0.05

# ---------- 1) 轻量认知体长跑（= 安装包真实运行路径）----------
from pasm.light import PASMAgent, PASMConfig
ag = PASMAgent(PASMConfig(seed=8), personality_seed=[0.5, 0.3, 0.6])
p0 = [ag._openness, ag._caution, ag._sociability]

tracemalloc.start()
marks = {}
t0 = time.perf_counter()
emo_light = []
for i in range(STEPS):
    r = rew(i)
    ag.learn([0.0] * 27, i % 4, [0.0] * 27, r)
    if i % 7 == 0:
        emo_light.append(float(ag.valence))
    if i == STEPS // 5 - 1:
        marks["b1"] = time.perf_counter() - t0
    if i == STEPS // 5 * 4 - 1:
        marks["b4"] = time.perf_counter() - t0
t_total = time.perf_counter() - t0          # 注意：perf_counter 是绝对时间，必须减去 t0
peak_cur, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()

first_seg = marks.get("b1", 0.0)
last_seg = t_total - marks.get("b4", t_total)
perf_ratio = (last_seg / first_seg) if first_seg > 1e-6 else 0.0

light_vec = [float(ag._openness), float(ag._caution), float(ag._sociability)]
light_in_range = 1 if all(-1.0 <= x <= 1.0 for x in light_vec) else 0
light_pin = 1 if all(0.02 < abs(x) < 0.98 for x in light_vec) else 0
light_drift = sum(abs(a - b) for a, b in zip(p0, light_vec))

half = len(emo_light) // 2
emo_drift = mean(emo_light[half:]) - mean(emo_light[:half])
emo_bounded = 1 if bounded(emo_light, -1.5, 1.5) else 0

# ---------- 2) 仿生层长跑（装了 torch 才跑）----------
if TORCH_OK:
    tier = "bionic"
    from pasm.modules.emotion import EmotionSystem, Personality
    pers = Personality(seed=[0.5, 0.3, 0.6])
    em = EmotionSystem()
    for i in range(STEPS):
        pers.shape(rew(i))
        em.update(reward=rew(i), rpe=rew(i) * 0.5, err_z=0.05)
    bp = [float(x) for x in pers.traits]
    bionic_pin = 1 if all(0.02 < abs(x) < 0.98 for x in bp) else 0
    bionic_bounded = 1 if all(-1.0 <= x <= 1.0 for x in bp) else 0
    bionic_vec = [round(x, 3) for x in bp]
    bionic_drift = round(sum(abs(x) for x in bp), 3)
else:
    tier = "light"
    bionic_pin = bionic_bounded = None
    bionic_vec = []
    bionic_drift = None

# ---------- 3) 行为长跑：熵会不会塌缩 ----------
from pasm.cognitive.learning import LearningEngine
eng = LearningEngine(seed=17)
eng.design({"energy": 0.7, "play": 0.6, "temper": 0.4}, 3, ACTS)
head, tail = Counter(), Counter()
for i in range(PICK_STEPS):
    a = eng.pick()
    if i < 500:
        head[a] += 1
    elif i >= PICK_STEPS - 500:
        tail[a] += 1
    if rew(i) > 0.3:
        eng.learn(action=a, delta=0.3)
entropy_delta = norm_entropy(tail) - norm_entropy(head)
tail_entropy = norm_entropy(tail)

# ---------- 4) 存档往返：一字不差地回来 ----------
eng2 = LearningEngine(seed=17)
eng2.design({"energy": 0.7, "play": 0.6, "temper": 0.4}, 3, ACTS)
eng2.apply_state(eng.state())
state_same = 1 if (eng2.weights == eng.weights and eng2.adj == eng.adj
                   and eng2.order == eng.order) else 0

pay = os.path.join(d, "learning.json")
eng3 = LearningEngine(data_path=pay, seed=17)
eng3.design({"energy": 0.7, "play": 0.6, "temper": 0.4}, 3, ACTS)
for i in range(300):
    eng3.learn(action=ACTS[i % len(ACTS)], delta=0.2)
eng3.save()
eng4 = LearningEngine(data_path=pay, seed=99)
file_same = 1 if (eng4.weights == eng3.weights and eng4.adj == eng3.adj) else 0

# ---------- 5) 记忆库长跑：容量不放水 ----------
for i in range(EPI_WARM):
    ML.episode_push("热身事件 %d" % i, "第 %d 段" % i, ["热身"], "日常",
                    salience=1 if i % 3 else 3)
mid_size = len(ML.episodes())
for i in range(EPI_FLOOD):
    ML.episode_push("洪峰事件 %d" % i, "第 %d 段" % i, ["洪峰"], "日常", salience=1)
final_size = len(ML.episodes())
cap = ML._EPI_CAP
mem_stable = 1 if final_size <= cap else 0
growth = final_size - cap

cleanup(d)
emit({
    "steps": STEPS, "pick_steps": PICK_STEPS, "tier": tier,
    "elapsed": round(t_total, 3), "peak_mb": round(peak / 1048576.0, 3),
    "perf_ratio": round(perf_ratio, 3),
    "first_seg": round(first_seg, 3), "last_seg": round(last_seg, 3),
    "light_vec": [round(x, 3) for x in light_vec], "light_in_range": light_in_range,
    "light_pin": light_pin, "light_drift": round(light_drift, 3),
    "bionic_vec": bionic_vec, "bionic_pin": bionic_pin,
    "bionic_bounded": bionic_bounded, "bionic_drift": bionic_drift,
    "emo_bounded": emo_bounded, "emo_drift": round(emo_drift, 3),
    "head_entropy": round(norm_entropy(head), 3), "tail_entropy": round(tail_entropy, 3),
    "entropy_delta": round(entropy_delta, 3),
    "state_same": state_same, "file_same": file_same,
    "mid_size": mid_size, "final_size": final_size, "cap": cap,
    "mem_stable": mem_stable, "growth": growth,
})
'''

# ------------------------------------------------------------------ 指标阈值
SPEC = [
    dict(key="perf_ratio", title="长跑不减速（后 20% 段耗时 / 前 20% 段）", hi=3.0,
         fmt="{:.3f}", bad="warn",
         note="显著大于 1 往往意味着隐藏的 O(n²) 或内存压力"),
    dict(key="light_in_range", title="轻量档人格长期在合法区间", lo=1, fmt="{:.0f}"),
    dict(key="light_pin", title="轻量档人格未被推到边界钉死", lo=1, fmt="{:.0f}",
         bad="warn",
         note="长期单向相处会把人格一路推到 ±1 并卡死 —— 装包（无 torch）跑的就是这一档"),
    dict(key="bionic_bounded", title="仿生档人格在合法区间", lo=1, fmt="{:.0f}"),
    dict(key="bionic_pin", title="仿生档人格未被推到边界钉死", lo=1, fmt="{:.0f}",
         bad="warn"),
    dict(key="emo_bounded", title="情绪长期有界", lo=1, fmt="{:.0f}"),
    dict(key="emo_drift", title="情绪均值未发散（后半 vs 前半）", lo=-0.6, hi=0.6,
         fmt="{:.3f}"),
    dict(key="tail_entropy", title="长跑之后行为仍有多样性（尾部熵）", lo=0.5,
         fmt="{:.3f}", bad="warn"),
    dict(key="entropy_delta", title="行为熵没有塌缩（尾部 - 头部）", lo=-0.35,
         fmt="{:.3f}", bad="warn", note="塌缩 = 跑久了只会做同一件事"),
    dict(key="state_same", title="状态往返一字不差（state → apply_state）", lo=1,
         fmt="{:.0f}", bad="fail"),
    dict(key="file_same", title="存档往返一字不差（save → load）", lo=1, fmt="{:.0f}",
         bad="fail"),
    dict(key="mem_stable", title="记忆库触顶后不再增长", lo=1, fmt="{:.0f}", bad="fail"),
    dict(key="growth", title="超容量增量（应为 0）", hi=0, fmt="{:.0f}"),
]


@register
class SoakLongrunAgent(Agent):
    """长效耐久验证：性能不衰减、记忆不膨胀、存档可往返、人格不钉死、行为不退化。

    用法：
        python -m pasm_skills run soak-longrun
    """

    name = "soak-longrun"
    goal = "长效耐久：性能衰减 / 记忆膨胀 / 存档往返 / 人格饱和 / 行为熵塌缩"
    needs = ("core",)

    def run(self):
        python, torch_ok = S.choose_python(self.ctx, prefer_torch=True)
        tier = "两档同测（含仿生层）" if torch_ok else "仅轻量档（无 torch）"

        res = S.run_scenario(self.ctx, SOAK_BODY, python=python, timeout=1800)
        m = S.metrics_of(res)
        if not m:
            self.fail("长效耐久场景未能运行", S.failure_detail(res))
            return None

        self.ok("长跑已跑完",
                "%s 步认知体 + %s 次行为选择 / %ss / 峰值内存 %sMB"
                % (m.get("steps"), m.get("pick_steps"), m.get("elapsed"),
                   m.get("peak_mb")))
        self.ok("记忆库容量表现",
                "%s 条（热身）→ %s 条（洪峰 %s 条后），容量上限 %s"
                % (m.get("mid_size"), m.get("final_size"),
                   m.get("final_size"), m.get("cap")))
        S.judge(self, m, SPEC, tier=tier)

        self.extra.update({"metrics": m, "python": S.python_label(python), "torch": torch_ok})
        return None
