# 发布指南（PUBLISH）

本仓产出**两个可上传的技能包**（同一份正文，两套 frontmatter）：

```
pasm-skills-dist/
├─ workbuddy/SKILL.md                        # WorkBuddy：SKILL.md 必须在根，ZIP 直接打这个目录
├─ clawhub/pasm-longterm-verify/SKILL.md     # ClawHub：要 slug 目录，目录里放 SKILL.md
└─ pasm-longterm-verify-0.2.1.zip            # ≤3MB，WorkBuddy 上传用（内含且仅含 SKILL.md）
```

**两份包的归档结构必须不同**，这是两个平台的硬要求，别为了统一而统一：

| 平台 | 期望结构 | 放错了会怎样 |
|---|---|---|
| WorkBuddy | ZIP **根目录**直接是 `SKILL.md` | 报「压缩包缺少 SKILL.md 文件」——它不递归找 |
| ClawHub | `<slug>/SKILL.md`（一层目录，网页上直接**选文件夹**） | 识别不到技能名 |

生成/更新（版本号自动取自 `pyproject.toml`，两边永不漂移）：

```bash
python tools/build_skill.py --zip           # 增量覆盖
python tools/build_skill.py --zip --clean   # 先把旧产物挪到 _stale/ 再重建（换结构后用这个）
```

脚本内置结构自检：ZIP 内容不等于 `['SKILL.md']` 会直接 `[FAIL]` 退出。

---

## 平台总览

| 平台 | 入口 | 状态 | 能自动化的部分 | 需要人工的部分 |
|---|---|---|---|---|
| **GitHub** | github.com/arronJack/pasm-skills | ✅ 已发布 | 全部（git push） | 无 |
| **Gitee** | gitee.com/arronzheng/pasm-skills | ✅ 已发布 | 全部（git push） | 无 |
| **本机 WorkBuddy** | `~/.workbuddy/skills/` | ✅ 已安装 | 全部（拷 SKILL.md） | 无 |
| **WorkBuddy 开放平台** | <https://open.workbuddy.cn/> | ✅ **已提交审核** | 除登录外的全部（浏览器自动化） | 仅微信扫码登录 |
| **ClawHub** | <https://clawhub.ai/skills/publish> | ✅ **已发布**（Hidden · Needs review） | 除登录外的全部 | 仅 GitHub 授权登录 |

---

## A. WorkBuddy 开放平台

### 实测记录（2026-09-12）

| 项 | 值 |
|---|---|
| 技能 ID | `os_0168b1aad6a492b8` |
| 市场展示名称 | PASM 长期验证智能体 |
| 市场展示分类 | 开发工具 |
| 服务类目 | 工具 - 办公 |
| 版本 | v0.2.1 |
| 状态 | **审核中**（平台提示：预计 7 个工作日内出结果） |
| 上传包 | `pasm-longterm-verify-0.2.1.zip`（5.2 KB） |

审核结果通过站内**通知**告知；通过后回技能列表点 **发布**，可见范围选 **公开发布**。
审核期间列表上有 **撤回** 按钮，可主动撤回重新提交。

### 包已满足的要求

| 要求 | 状态 |
|---|---|
| ZIP ≤ 3MB | ✅ 约 5.2 KB |
| **ZIP 根目录直接是 `SKILL.md`** | ✅ 无中间层级（`skills/`、`{name}/` 都不要） |
| 技能名规范（小写 + 短横线） | ✅ `pasm-longterm-verify` |
| frontmatter 必填 `description` / `description_zh` / `description_en` / `version` / `author` | ✅ 全部具备 |
| `name` / `display_name` / `display_name_en` / `license` / `homepage` | ✅ 附带 |
| `requires.bins` / `requires.python` | ✅ `[python3, git]` / `>=3.10` |

> 平台会自动解析 frontmatter 生成「市场展示名称 / 介绍 / 版本号」，并给一个首字母默认头像。
> 需要人工补的只有两项：**市场展示分类**（多选）和**服务类目**（一级 + 二级，至少 1 个）。
> 「试试这样问我」示例问句当前为空 —— 平台从包内某个字段读，本仓 SKILL.md 未提供。

### 操作步骤（浏览器自动化实走一遍的版本）

1. 打开 <https://open.workbuddy.cn/>，微信扫码登录（**这一步必须本人做**，其余可自动）；
2. 左侧 **发布管理 → 技能 → 创建**；
3. 上传 ZIP：`pasm-skills-dist/pasm-longterm-verify-0.2.1.zip`；
4. 解析通过后页面显示「类型：技能 / 技能ID：`os_…`」，点 **继续**；
5. 第 2 步「确认信息」补两个必填项：
   - **市场展示分类** → 选 `开发工具`（可多选，多余的标签点 × 删掉）；
   - **服务类目** → 一级选 `工具`，二级选 `办公`；
6. 点 **继续** → 第 3 步核对全部信息 → 点 **提交**；
7. 提示「已提交审核，预计 7 个工作日内出结果」。

### 上传前自检

```bash
python -c "import zipfile;z=zipfile.ZipFile('E:/AI/pasm-skills-dist/pasm-longterm-verify-0.2.1.zip');print(z.namelist())"
# 期望：['SKILL.md']      ← 不是 ['skills/pasm-longterm-verify/SKILL.md']
```

---

## B. ClawHub（qclaw 技能市场）

⚠️ **ClawHub 强制 MIT-0 许可证**。本仓源码是 MIT，发布到 ClawHub 的那份包
按平台要求标注 `license: MIT-0`（比 MIT 更宽松，允许无署名使用）。
`clawhub/<slug>/SKILL.md` 里的 `license` 已经写成 `MIT-0`，
是**故意与源码仓不一致**的 —— 发布前请确认接受这一点。

### 实测记录（2026-09-12）

| 项 | 值 |
|---|---|
| 发布账号 | `@arronjack`（Sign in with GitHub） |
| Slug | `pasm-longterm-verify` |
| Display name | `PASM Long-term Verification` |
| Summary | 由 SKILL.md 的 `description` 自动带入（300/300 字符上限） |
| Version | `0.2.1` —— ⚠️ **平台默认填 `1.0.0`，必须手动改** |
| Categories | Research / Development / Agents（3/3） |
| Keywords | `#pasm #verification #memory #testing #ai-agents`（5/5） |
| License | MIT-0（强制，须勾选权利声明才能发布） |
| 状态 | **Hidden · Needs review**；面板提示「SkillSpector findings are pending for this release」 |

> ClawHub 发完不是立刻公开：它先跑 **SkillSpector** 自动扫描，扫描结果出来后才进审核/上架。
> 在此之前技能处于 `Hidden from public catalog`。

### 流程（网页方式）

1. 打开 <https://clawhub.ai/skills/publish> → **Sign in with GitHub**；
2. 拖拽或点 **Choose folder**，选目录 `pasm-skills-dist/clawhub/pasm-longterm-verify/`
   （控件是 `input[webkitdirectory]`，要的是**文件夹**不是压缩包）；
3. 平台自动解析并预填 SLUG / SUMMARY / RELEASE TAGS；**VERSION 默认 `1.0.0` 要手改成 `0.2.1`**；
4. 补 DISPLAY NAME、**CATEGORIES**（最多 3 个）、**SEARCH KEYWORDS**（最多 5 个）；
5. 勾选 **I have the rights to publish this skill under MIT-0.**（required）；
6. 点 **Publish skill** → 跳 Dashboard，技能卡片显示 `Hidden` / `Needs review`。

### 方式 1：CLI（可版本化，适合以后自动化）

```bash
npx clawhub@latest publish E:/AI/pasm-skills-dist/clawhub/pasm-longterm-verify \
  --slug pasm-longterm-verify \
  --name "PASM Long-term Verification" \
  --version 0.2.1 \
  --changelog "领域智能体：NPC 长期生命 / 老人陪伴 / 学习陪伴 / 长效耐久；修 3 处核心缺陷与 1 处验证器自身缺陷" \
  --tags latest
```

- `slug` 必须小写 + 短横线；`version` 必须是合法 semver；
- 首次使用需要先 `npx clawhub@latest login`（浏览器授权）。

### 方式 2：从 GitHub 导入

ClawHub 支持按 GitHub 仓库导入，但要求：仓库**公开**、**非 fork**、且**属于当前登录账号**。
`github.com/arronJack/pasm-skills` 三条都满足 —— 但注意导入按**仓库根**找 SKILL.md，
本仓根目录没有（正文在 `skill/SKILL.body.md`），所以**这种方式不适用**，用上面的文件夹上传。

### frontmatter 已满足的 ClawHub 要求

| 要求 | 状态 |
|---|---|
| `name` 匹配 `^[a-z0-9][a-z0-9-]*$` | ✅ `pasm-longterm-verify` |
| `description` | ✅ |
| `version` semver | ✅ `0.2.1`（但网页表单不自动读，要手填） |
| `metadata.openclaw.requires.env` / `.bins` | ✅ `[]` / `[python3, git]` |
| `license` | ✅ `MIT-0` |

---

## C. 本机 WorkBuddy（已经装好，立即能用）

```bash
# 安装（已执行过一次）
mkdir -p ~/.workbuddy/skills/pasm-longterm-verify
cp pasm-skills-dist/workbuddy/SKILL.md \
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
python tools/build_skill.py --zip --clean
# 3) WorkBuddy：后台上传新 ZIP（同技能名 → 新版本号）
# 4) ClawHub：重跑 publish，--version 用新号（网页方式记得手改 VERSION 框）
# 5) 本机技能：重新 cp 一份
```

---

## E. 踩过的坑（都已在工具链里固化）

| 坑 | 现象 | 处理 |
|---|---|---|
| **ZIP 结构放错** | 传 `skills/<name>/SKILL.md` → 平台报「压缩包缺少 SKILL.md 文件」 | 平台只认**根目录**的 SKILL.md，不递归。`build_skill.py` 已改为根目录输出 + 结构自检 |
| **上传后 DOM 被重建** | 再对该页面 `upload` 会报 `Element not found`（`input[type=file]` 被 React 移除了） | 先 `open` 同一 URL 重新加载页面，再 `upload` |
| **元素 ref 会失效** | 用快照里的 `@e12` 点击，点到了别的链接（跳去 ClawHub） | 每次操作前重新快照；或直接用 `eval` 按文本查元素再点 |
| **自定义下拉不响应 `eval` 的 `.click()`** | 派发 `click` 事件后下拉纹丝不动（组件监听的是 pointer 事件） | 改用真实鼠标：`mouse move <x> <y>` → `mouse down` → `mouse up`；坐标用 `getBoundingClientRect()` 取，**不要**照截图估 |
| **截图坐标 ≠ 视口坐标** | 截图 1080 宽、视口 1867 宽，按截图估的坐标全偏 | 一律 `eval` 取 `getBoundingClientRect()`，或先读 `innerWidth` 算缩放 |
| **ClawHub 的 VERSION 不自读** | 表单默认 `1.0.0`，与包内 `0.2.1` 不一致 | 发布前手动改；否则两边版本号会对不上 |
| **中文乱码** | PowerShell 输出 `寮€鍙戝钩鍙?` | 命令前加 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` |
| **`ind()` 折行** | YAML `>-` 折叠时中文句子中间多出空格 | 中文描述整体输出一行不折行，别改回去 |

---

MIT © arronZheng（小志）
