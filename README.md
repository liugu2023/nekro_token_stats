# Nekro Token Stats

消耗统计插件，用于统计 Nekro Agent 当日 AI Token 与字符消耗，并支持按群聊范围查询。

## 功能

- 查询当日 Token 总消耗、输入 Token、输出 Token
- 查询当日字符消耗
- 默认统计当前群聊
- 支持全局统计、详细模式和指定群聊筛选
- 提供沙盒方法供 AI 获取统计数据

## 使用

将本目录放入 Nekro Agent 插件工作目录后启用插件：

```text
data/nekro_agent/plugins/workdir/nekro_token_stats
```

插件模块名为：

```text
nekro_token_stats
```

## 命令

- `token_stats` 或 `ts`：统计当前群聊当日消耗
- `ts -detail`：显示详细数值
- `ts -all`：统计全部群聊
- `ts -all -detail`：统计全部群聊并显示详细数值
- `ts -c group1,group2`：统计指定群聊

## 许可证

MIT
