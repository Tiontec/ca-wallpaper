# AGENTS.md

任务涉及 iOS 锁屏壁纸（`.tendies` / `.ca` / 景深 / 深浅色按钮 / 壁纸库转圈）时：

1. 先读 `SKILL.md`（尤其 §1 事实表与 §4 铁律），再动手。
2. 工具在 `scripts/tendies.py`（依赖仅 Pillow）。景深修复 = `inspect` → `flatten`(目视检查) → `graft`(v1/v2/v3 逐版) → `validate`。
3. 模板包已内置在 `templates/`（需用户先在手机上确认其景深正常）；不要在坏包上补字段；不要手写 `main.caml`。
4. 你没有真机：不要声称"已经有景深"，只说"结构自检通过，请在锁屏验证"。
5. 无法运行代码时，见 `SKILL.md` §7。
6. 完整提示词版本：`PROMPT_FOR_ANY_AI.md`。
