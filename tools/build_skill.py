"""构建基座仓自己的技能包（一份：教人怎么写 PASM 智能体）。

规则全在 `pasm_skills.build` 里（归档结构、frontmatter、ZIP 自检）——
基座仓只声明"我有哪些技能"。你自己的仓照抄这个文件，换掉 `SKILLS` 即可。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pasm_skills.build import ProjectMeta, SkillSpec, run_cli  # noqa: E402

META = ProjectMeta(
    author="arronzheng",
    homepage="https://github.com/arronJack/pasm-skills",
    repository="https://gitee.com/arronzheng/pasm-skills",
)

SKILLS = [
    SkillSpec(
        name="pasm-agent-authoring",
        body_file="SKILL.authoring.body.md",
        display_name_zh="PASM 智能体开发基座",
        display_name_en="PASM agent authoring kit",
        desc_zh=(
            "PASM 智能体开发基座——从零写一个基于 PASM 引擎的智能体并打成可发布技能包。"
            "当需要给自己的游戏/应用加一个会记忆、有情绪、能被反馈塑形的智能体，"
            "需要 SDK 的 BaseAgent 用法、动作池与回复模板怎么写、档位怎么降级、"
            "状态怎么持久化，或需要把智能体打成平台可上传的技能包时使用。"
            "零 LLM 依赖、断网可用、只用标准库。"
            "关键词：PASM、智能体基座、BaseAgent、SDK、写智能体、记忆、情绪、"
            "场景仿真、技能包打包、SKILL.md、zip-root、slug-dir。"
        ),
        desc_en=(
            "PASM agent authoring kit - build your own agent on the PASM cognitive engine from "
            "scratch, then package it as a publishable skill. Use when adding a memory/emotion/"
            "feedback-shaped agent to your game or app, when you need the BaseAgent SDK, action "
            "pool and reply-template patterns, tier degradation, persistent state, or when "
            "packaging an agent into an uploadable skill (zip-root / slug-dir layouts). "
            "Zero LLM dependency, offline-runnable, stdlib only. "
            "Keywords: pasm, agent framework, BaseAgent, SDK, build agent, memory, emotion, "
            "scenario simulation, skill packaging."
        ),
        plain_desc=(
            "The base kit for building agents on the PASM cognitive engine. Ships a BaseAgent SDK "
            "(observe / recall / mood / act / feedback / save with persistent JSON state), an agent "
            "framework (registry, isolated repo probing, scenario simulation harness, core-contract "
            "check toolboxes) and a skill-packaging library producing the two archive layouts "
            "platforms require. Write an agent by subclassing BaseAgent and implementing an action "
            "pool plus a reply template; the engine tier (light / core / bionic) is always reported, "
            "never hidden. Zero LLM dependency, offline-runnable, stdlib only."
        ),
        plain_category="developer-tools",
        plain_tags=["pasm", "agent-framework", "sdk", "ai-agents", "authoring"],
        plain_license="MIT-0",
    ),
]

if __name__ == "__main__":
    raise SystemExit(run_cli(SKILLS, META, root=ROOT))
