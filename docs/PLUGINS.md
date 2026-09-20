# 插件放在哪里（基座侧约定）

> 完整决策见 `pasm-framework` 仓的 `docs/plugin-ownership.md`。这里是**基座视角的速查**。

## 一句话

**内置插件放本仓子目录；外部插件放任何包都行（靠 entry-point 自动发现）；不建两个 plugin 仓。**

| 类别 | 位置 | 版本策略 |
| --- | --- | --- |
| **A. 基座内置插件**（官方维护） | 本仓 `pasm_skills/plugins/` | **跟随基座版本**，不单独发版 |
| **B. 第三方插件**（别人写的） | 各自的包，任何仓都行 | 自己发版，靠 entry-point 被发现 |
| **C. 官方独立节奏的插件**（日后真有再说） | 建**一个** `pasm-plugins` 仓，内部分 `skills/` 与 `framework/` | 独立版本号 |

## 为什么内置插件不放独立仓

它们直接使用内核内部 API（`BaseAgent` 的 `_core` / `_episodes`、Hook 名、私有字段）。
一旦分仓，就会出现「装上新插件 + 旧内核 → `ImportError`」这类**静默的版本漂移**，
而且每次内核改动都要跨仓发版四次（两仓 × 两端），极易漏同步。

## 为什么外部插件不指定官方仓

框架侧的 entry-point 机制已经工作：

```toml
[project.entry-points."pasm_framework.plugins"]
my_plugin = "my_pkg.my_module:MyPlugin"
```

插件可以住在**任何** PyPI 包里，框架启动时自动发现。给外部插件指定一个官方仓，
反而会传递"只有官方仓里的才算插件"的错误暗示。

## 基座侧插件（A 类）的硬要求

1. 只用**已导出**的稳定表面（`pasm_skills.sdk`），不要 import 内部模块；
2. 读配置一律 `self.config.get(k, default)` —— 硬索引缺键会**启动即崩且零提示**；
3. 自带 `selftest`，并保证 `python -m pasm_skills selftest` 仍全绿；
4. 不引入强制依赖（基座承诺零依赖可跑；重依赖必须是可选 extra）。

## 什么条件才建 `pasm-plugins` 仓

三条**同时**满足：① 官方维护；② 有独立发布节奏；③ 不是"成品智能体"（那些去 `pasm-agents`）。
建的时候是**一个仓**（顶层 `skills/` + `framework/` 两个目录，多包单仓），
而不是 `pasm-skills-plugin` + `pasm-framework-plugin` 两个仓 ——
因为一个插件常常同时用到两层（例：智能客服 = 框架层网关 + 基座层记忆），
两个仓会把它劈成两半。
