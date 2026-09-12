# 发布指南（PUBLISH）

本仓产出**两个可上传的技能包**（同一份正文，两套 frontmatter）：

```
pasm-skills-dist/
├─ workbuddy/skills/pasm-longterm-verify/SKILL.md    # WorkBuddy 开放平台
├─ clawhub/pasm-longterm-verify/SKILL.md             # ClawHub（qclaw 技能市场）
└─ pasm-longterm-verify-0.2.1.zip                    # ≤3MB，WorkBuddy 上传用
```

生成/更新（版本号自动取自 `pyproject.toml`，两边永不漂移）：

```bash
python tools/build_skill.py --zip
```

---

## 平台总览

| 平台 | 入口 | 能自动化的部分 | 需要人工的部分 |
|---|---|---|---|
| **GitHub** | github.com/arronJack/pasm-skills | ✅ 全部（git push） | 无 |
| **Gitee** | gitee.com/arronzheng/pasm-skills | ✅ 全部（git push） | 无 |
| **本机 WorkBuddy** | `~/.workbuddy/skills/` | ✅ 全部（拷 SKILL.md） | 无 |
| **WorkBuddy 开放平台** | <https://open.workbuddy.cn/> | ❌ 无法 API 上传 | **开发者入驻认证 + 后台上传 + 人工审核** |
| **ClawHub** | <https://clawhub.ai/import> | ⚠️ 有 CLI，但需 token | **获取 token / 登录** |

> 为什么前两个平台不能全自动：它们都要求**账号身份与开发者资质**，
> 上传动作绑定在已登录的网页会话或 CLI token 上。这部分必须由账号持有人操作。

---

## A. WorkBuddy 开放平台

### 包已满足的要求

| 要求 | 状态 |
|---|---|
| ZIP ≤ 3MB | ✅ 约 5.3 KB |
| 目录结构 `skills/{skill-name}/SKILL.md`（最多 2 层） | ✅ 无多余层级 |
| 技能名规范 | ✅ `pasm-longterm-verify` |
| frontmatter 必填 `description` / `description_zh` / `description_en` / `version` / `author` | ✅ 全部具备 |
| `name` / `display_name` / `display_name_en` / `license` / `homepage` | ✅ 附带 |
| `requires.bins` / `requires.python` | ✅ `[python3, git]` / `>=3.10` |

### 操作步骤

1. 打开 <https://open.workbuddy.cn/>，用开发者账号登录；
2. 若未入驻：先完成**开发者认证**（个人/企业资料审核）；
3. 进入左侧 **发布管理 → 技能 → 创建**；
4. 上传 ZIP：`pasm-skills-dist/pasm-longterm-verify-0.2.1.zip`；
5. 核对自动解析出的信息（名称/版本/描述/触发词），必要时微调；
6. **提交审核**（实测约 18 小时）；
7. 审核通过后回到列表，点 **发布**，可见范围选 **公开发布**。

### 上传前自检

```bash
python -c "import zipfile;z=zipfile.ZipFile('E:/AI/pasm-skills-dist/pasm-longterm-verify-0.2.1.zip');print(z.namelist())"
# 期望：['skills/pasm-longterm-verify/SKILL.md']
```

---

## B. ClawHub（qclaw 技能市场）

⚠️ **ClawHub 强制 MIT-0 许可证**。本仓源码是 MIT，发布到 ClawHub 的那份包
按平台要求标注 `license: MIT-0`（比 MIT 更宽松，允许无署名使用）。
若不想以 MIT-0 发布，就不要走 ClawHub，只走 WorkBuddy + GitHub + Gitee。

### 方式 1：CLI（推荐，可版本化）

```bash
npx clawhub@latest publish E:/AI/pasm-skills-dist/clawhub/pasm-longterm-verify \
  --slug pasm-longterm-verify \
  --name "PASM Long-term Verification" \
  --version 0.2.1 \
  --changelog "领域智能体：NPC 长期生命 / 老人陪伴 / 学习陪伴 / 长效耐久；修 3 处核心缺陷与 1 处验证器自身缺陷" \
  --tags latest
```

- `slug` 必须小写 + 短横线；
- `version` 必须是合法 semver；
- 首次使用需要先 `npx clawhub@latest login`（浏览器授权）。

### 方式 2：网页上传文件夹

1. 打开 <https://clawhub.ai/import>；
2. 上传目录 `pasm-skills-dist/clawhub/pasm-longterm-verify/`；
3. 只接受文本文件；**不要**包含 `.git` / `LICENSE` / 图片 / `.DS_Store`（当前包只有 `SKILL.md`，已合规）；
4. 确认 slug / 版本 / 描述后提交。

### 方式 3：从 GitHub 导入

ClawHub 支持按 GitHub 仓库导入，但要求：仓库**公开**、**非 fork**、且**属于当前登录账号**。
`github.com/arronJack/pasm-skills` 三条都满足。

### frontmatter 已满足的 ClawHub 要求

| 要求 | 状态 |
|---|---|
| `name` 匹配 `^[a-z0-9][a-z0-9-]*$` | ✅ `pasm-longterm-verify` |
| `description` | ✅ |
| `version` semver | ✅ `0.2.1` |
| `metadata.openclaw.requires.env` / `.bins` | ✅ `[]` / `[python3, git]` |
| `license` | ✅ `MIT-0` |

---

## C. 本机 WorkBuddy（已经装好，立即能用）

```bash
# 安装（已执行过一次）
mkdir -p ~/.workbuddy/skills/pasm-longterm-verify
cp pasm-skills-dist/workbuddy/skills/pasm-longterm-verify/SKILL.md \
   ~/.workbuddy/skills/pasm-longterm-verify/SKILL.md
```

装好后在当前会话里说"跑一下 PASM 长期验证"即可触发。

**安全说明**：包里只有一个 `SKILL.md`（纯 Markdown，约 10 KB），
不含脚本、不含二进制、不含网络回调；它只是教智能体去 `git clone` 本仓并运行 CLI。
已核查：无 `<script>`、无 `curl|sh` 管道、无 `rm -rf`。

---

## D. 更新发布版本

```bash
# 1) 改 pyproject.toml 的 version（单一来源）
# 2) 重新生成两个包 + ZIP
python tools/build_skill.py --zip
# 3) WorkBuddy：后台上传新 ZIP（同技能名 → 新版本）
# 4) ClawHub：重跑 publish，version 用新号
```

`tools/build_skill.py` 里 `ind()` 对中文**不折行** —— 因为 YAML 的 `>-`
会把换行折叠成空格，中文被折开后会多出突兀的空格。这是踩过的坑，别改回去。

---

MIT © arronZheng（小志）
