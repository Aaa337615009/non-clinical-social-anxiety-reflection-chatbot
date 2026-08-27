# Non-clinical Social Anxiety Reflection Chatbot — MVP

这是一个手机优先的非临床研究 MVP。参与者通过 Streamlit 聊天页面回顾社交情境，研究人员通过独立、密码保护的 Dashboard 实时监看会话。应用使用 OpenAI Responses API 的 Structured Outputs 约束每轮结果，并使用 Supabase PostgreSQL 保存研究数据。

> 重要：本项目不是诊断、治疗或紧急支持服务。投入真实研究前，仍需完成伦理审批、数据保护影响评估、研究人员风险升级流程、本地化危机资源审核、可用性测试和安全审查。

## 已实现功能

- English-only 的参与者界面、对话文案与 Researcher Dashboard
- Home、Reflect、Reflections、Support、Settings 五个参与者端视图及固定底部导航
- pastel aurora + soft glassmorphism 手机优先界面，支持 `prefers-reduced-motion`
- 10 个内部状态按完成条件顺序运行，并映射为参与者可见的 8 个阶段；Stage 5 显示 5.1/5.2/5.3 子阶段
- Stage 3 使用 Structured Output 语义维护 event、response、thought、emotion 四个 case slots（含来源、置信度与澄清标记），只追问真正缺失的一项
- Stage 4 在进入苏格拉底式探索前解释理由并要求明确许可；没有许可时不会推进
- Participant ID 与实时监看知情同意
- Skip 与带二次确认的 End；旧 paused 数据保持兼容但不再提供 Pause/Resume 操作入口
- 每轮最多一个主要问题；根据情绪强度和近期对话决定是否以及多长地确认感受，避免模板化重复
- 明确的非临床边界：不诊断、不治疗、不把推断说成事实
- 多语言确定性风险词检测；明显紧急风险会绕过模型，并以英国英语进入危机支持路径
- 对 “I don't know” 及等价输入提供英文低负担追问与 2–3 个英文 quick replies
- 全程 End 入口会先询问是否生成卡片；Stage 6 完成后也先让参与者选择卡片、继续谈或结束
- 可 Edit、Regenerate、Delete、Save 的结构化 Reflection Card；包含 2–4 个明确标记为可能性的解释，且保存前仅为草稿
- 用户消息即时呈现，模型等待状态显示在同位置的 assistant loading bubble；失败时保留消息并显示安全重试提示
- sticky 八阶段进度条和统一消息圆角；End、会话数据删除和退出研究均提供确认路径
- 独立密码保护 Researcher Dashboard，每 2 秒重新读取 Supabase
- `sessions`、`messages`、`feedback` 表、约束、索引、RLS 和默认拒绝权限
- 无 Supabase/OpenAI 密钥时可运行本地演示（进程重启后数据丢失）

OpenAI 调用采用官方文档所示的 Python Pydantic 方式：`client.responses.parse(..., text_format=AssistantTurn)`，再读取 `response.output_parsed`。请求显式设置 `store=False`，但研究团队仍需依据所用账户的数据控制设置与机构政策确认处理方式。参见 [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)。

## 项目结构

```text
app.py                              # 参与者手机端页面
pages/1_Researcher_Dashboard.py     # 独立研究人员 Dashboard
reflection_app/
  engine.py                         # Responses API、状态约束和演示引擎
  models.py                         # Pydantic 输出模型和状态机
  prompts.py                        # English-only 非临床对话规范及阶段目标
  ui_copy.py                        # English-only 参与者界面文案
  safety.py                         # 确定性风险识别和危机路径
  repository.py                     # Supabase / 内存仓储
sql/schema.sql                      # 数据库、安全约束和 RLS
tests/                              # 核心逻辑单元测试
```

## 本地运行

要求 Python 3.11+。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
streamlit run app.py
```

不填写 Supabase 配置时会自动进入本地内存模式；不填写 OpenAI key 时会使用确定性演示对话。也可以显式设置 `DEMO_MODE=true`。演示模式只能用于 UI 评估，不能保存真实研究数据。

参与者页面通常为 `http://localhost:8501/`，Dashboard 通常为 `http://localhost:8501/Researcher_Dashboard`。

## Supabase 配置

1. 创建 Supabase 项目，在 SQL Editor 完整运行 [`sql/schema.sql`](sql/schema.sql)。
2. 从 Supabase 项目设置取得 Project URL 与 `service_role` key。
3. 将值仅写入本地 `.streamlit/secrets.toml` 或部署平台的 Secret 管理界面。
4. 设置一个长且随机的 `RESEARCHER_DASHBOARD_PASSWORD`。
5. 将 `DEMO_MODE` 设为 `false`，重启应用并先用测试 Participant ID 验证写入和 Dashboard 刷新。

安全设计：数据库对 `anon` 与 `authenticated` 均无 RLS policy 并显式撤销表权限；只有运行在服务端的 Streamlit 使用 `service_role`。绝不能把 `SUPABASE_SERVICE_ROLE_KEY` 放进浏览器代码、URL、日志、Git 或截图。生产研究建议进一步使用单独后端、机构身份认证、密钥轮换、审计日志、备份/保留策略和最小权限数据库函数。

## OpenAI 与环境配置

应用依次读取环境变量或 Streamlit secrets：

| 名称 | 必需 | 说明 |
|---|---:|---|
| `OPENAI_API_KEY` | 真实模型需要 | 仅服务端保存 |
| `OPENAI_MODEL` | 否 | 默认 `gpt-5-mini`，须选支持 Structured Outputs 的可用模型 |
| `SUPABASE_URL` | 持久化需要 | Supabase Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | 持久化需要 | 高权限服务端密钥 |
| `RESEARCHER_DASHBOARD_PASSWORD` | Dashboard 需要 | 未配置时 Dashboard 默认关闭 |
| `DEMO_MODE` | 否 | `true` 强制内存存储 |
| `CRISIS_SUPPORT_TEXT` | 建议本地化 | 研究团队审批后的危机支持文案 |

`.gitignore` 已排除 `.streamlit/secrets.toml`、`.env`、`.env.*` 和常见私钥文件；示例文件只含占位符。

## 危机支持路径

默认文案以英国为例：如果本人或他人处于立即危险中，联系 999 或前往 A&E；紧急心理健康帮助可联系 NHS 111；Samaritans 可免费拨打 116 123。来源：[NHS urgent mental health help](https://www.nhs.uk/nhs-services/mental-health-services/where-to-get-urgent-help-for-mental-health/) 与 [Samaritans](https://www.samaritans.org/how-we-can-help/contact-samaritan/)。

真实部署前必须根据参与者所在地、年龄范围、研究方案和伦理审批替换 `CRISIS_SUPPORT_TEXT`。关键词规则只用于保守标记，不能判定一个人的真实风险，也不能替代训练有素的人工评估。Dashboard 的风险标记必须对应研究团队已批准且有人值守的升级流程。

## 测试

```bash
pytest -q
python -m compileall app.py pages reflection_app tests
```

测试覆盖状态顺序与防跳转、单一问题约束、风险拦截、知情同意、Participant ID 校验、消息/反馈保存及总结卡删除。API 与 Supabase 的在线集成测试需要测试项目和测试密钥，本地单元测试不会读取真实密钥或访问网络。

## Streamlit 部署说明（待你确认后执行）

本轮不会发布。确认后可将仓库连接到 Streamlit Community Cloud 或机构批准的容器平台，入口为 `app.py`，并在平台 Secret 管理中配置与 `.streamlit/secrets.toml.example` 相同的键。部署前至少完成：

1. 使用非生产 Supabase 项目验证 SQL、RLS、写入与删除行为。
2. 将危机文案与研究人员升级流程本地化并由负责人批准。
3. 确认数据区域、保留期、参与者撤回/删除流程及访问审计。
4. 将简单共享密码升级为机构 SSO 或其他适合研究数据的认证方案。
5. 运行依赖与代码安全扫描，并在手机上完成端到端测试。
