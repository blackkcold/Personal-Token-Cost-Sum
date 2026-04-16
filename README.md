# OpenCode Token 使用报告

基于 [OpenCode](https://opencode.dev/) 的 Token 消耗可视化仪表盘。

**在线访问：** https://blackkcold.github.io/Personal-Token-Cost-Sum/

## 功能

- 📊 **Token 消耗统计** - 总计、日均、月均预测
- 💰 **成本分析** - 美元/人民币双币种显示
- 📈 **趋势图表** - 每日消耗趋势、模型分布、Provider 对比
- 🏆 **性价比排行** - 各 Provider 性价比对比（支持订阅制/按量计费）
- 📋 **详细数据表** - 支持按日期、模型、Provider 筛选

## 订阅制定价

| Provider | 月费 | 备注 |
|----------|------|------|
| Minimax | ¥29/月 | 不限 Token，限制请求次数 |
| 小米 | ¥34.9/月 | 不限 Token |
| OpenAI Plus | $19.99/月 | GPT-4 等 |
| OpenCode Go | $10/月 | Coding Plan，可叠加 API 超额 |

## 本地运行

1. 安装 OpenCode
2. 运行 Token Tracker 生成数据：
   ```bash
   python3 token_tracker.py json
   python3 token_tracker.py html
   ```
3. 使用 VS Code Live Server 或上传至 GitHub Pages 访问

## 数据来源

数据来自 OpenCode 本地数据库 `~/.local/share/opencode/opencode.db`，仅包含使用 OpenCode 时的 API 消耗统计。

## 页面预览

![Dashboard Preview](https://img.shields.io/badge/Dashboard-Token%20Tracker-blue)

---

*此页面仅展示个人使用统计，不包含任何敏感信息。*