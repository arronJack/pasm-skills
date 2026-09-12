# 事实基线（baselines/）

`regression` 智能体把「某个时间点 PASM 确实长什么样」记在这里，之后每次运行
自动与基线比对，任何静默退化（文件被删、模块消失、契约版本回退）都会被抓出来。

```bash
python -m pasm_skills run regression --update            # 建立/刷新基线（默认名 core）
python -m pasm_skills run regression --baseline v0285    # 用指定基线名
python -m pasm_skills run regression                     # 与基线比对（默认 core）
```

## 建议入库

**基线文件应当随仓库提交** —— 它的价值就在于"跨时间可比"。
只有提交了，三个月后拉下来跑一次才知道中间有没有退化。

基线内容（`core.json` 示例结构）：

```json
{
  "collected_at": "2026-09-12 13:40:00",
  "core": {
    "cognitive": { "symbolic.py": "3f2a...", "memrouter.py": "9c14..." },
    "api": "1.0",
    "engines": ["pasm", "pasm-light"]
  },
  "lite": {
    "files": { "engine.py": "aa01...", "learning.py": "7b3d..." },
    "engines": ["pasm-lite"]
  }
}
```

## 命名建议

- `core.json` —— 主线基线，随每次正式发版刷新；
- `v0285.json`、`v0290.json` —— 按版本留档，便于"从这个版本之后开始退化"的定位。

## 注意

基线**不判断好坏**，只记录差异。文件变了会报 `[WARN]`（可能是本次的正常改动，
也可能是意外），文件**消失**会报 `[FAIL]`。看到 WARN 请结合当次改动判断：
预期之内就用 `--update` 刷新基线，意外就往下查。
