"""
# 消耗统计姬 (TokenStats)

统计 AI 消耗的 Token 和字符数量，支持精简摘要、详细明细及按群聊筛选模式。

## 主要功能

- **当日消耗统计**: 默认只统计当前群聊的 Token 和字符消耗。
- **全局模式**: `-all` 统计所有群聊并分组展示。
- **详细模式**: `-detail` 显示完整数值。
- **指定群聊**: `-c group1,group2` 只统计指定群聊（英文逗号分割）。
- **沙盒方法**: 可在代码执行中调用方法获取统计数据。

## 使用方法

- **当前群聊**: `token_stats` 或 `ts`
- **详细模式**: `ts -detail`
- **全部群聊**: `ts -all`
- **全部详细**: `ts -all -detail`
- **指定群聊**: `ts -c group_xxx,group_yyy`
- **沙盒调用**: `get_token_stats(chat_keys=None, detail=False)`

## 统计口径

- **Token & 字符统计**: 来自数据库记录（每次执行的 SandboxCodeExtData）
- **时区**: UTC 日期起始（00:00:00 UTC）
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional

from nekro_agent.api import i18n
from nekro_agent.api.plugin import NekroPlugin, SandboxMethodType
from nekro_agent.models.db_exec_code import DBExecCode
from nekro_agent.services.command.base import CommandPermission
from nekro_agent.services.command.ctl import CmdCtl
from nekro_agent.services.command.schemas import Arg, CommandExecutionContext, CommandResponse

plugin = NekroPlugin(
    name="消耗统计姬",
    module_name="nekro_token_stats",
    description="统计 AI 消耗的 Token 和字符数量",
    version="0.4.0",
    author="liugu",
    url="https://github.com/liugu2023/nekro_token_stats",
    support_adapter=["onebot_v11", "telegram", "discord", "feishu", "wxwork"],
    i18n_name=i18n.i18n_text(
        zh_CN="消耗统计姬",
        en_US="Token Stats",
    ),
    i18n_description=i18n.i18n_text(
        zh_CN="统计 AI 消耗的 Token 和字符数量",
        en_US="统计 AI 消耗的 Token 和字符数量",
    ),
    sleep_brief="用于统计 Token 和字符消耗，在需要查询消耗时激活。",
)


def _get_today_date_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def _today_start_utc() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _fmt_k(n: int) -> str:
    """将数字格式化为紧凑的 k 单位字符串，例如 12345 -> 12.3k"""
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _parse_flags(raw: str) -> tuple[bool, bool, list[str]]:
    """解析标志参数，返回 (show_all, detail, chat_keys)"""
    show_all = bool(re.search(r"-all\b", raw, re.IGNORECASE))
    detail = bool(re.search(r"-detail\b", raw, re.IGNORECASE))

    chat_keys: list[str] = []
    m = re.search(r"-c\s+([\S]+)", raw)
    if m:
        chat_keys = [k.strip() for k in m.group(1).split(",") if k.strip()]

    return show_all, detail, chat_keys


async def get_token_stats_async(
    chat_keys: Optional[list[str]] = None,
    detail: bool = False,
) -> dict:
    """获取当日 Token 和字符统计

    Args:
        chat_keys: 要统计的群聊列表；None 表示全局（所有群聊）；空列表等同于 None
        detail: 是否包含各群聊分组明细（仅在 chat_keys 为 None/多个时有效）

    Returns:
        dict: 统计信息
    """
    today = _get_today_date_str()
    query = DBExecCode.filter(create_time__gte=_today_start_utc())

    # 确定是否需要按群聊分组
    multi_group = not chat_keys or len(chat_keys) > 1
    if chat_keys:
        query = query.filter(chat_key__in=chat_keys)

    fetch_fields = ["chat_key", "extra_data"] if multi_group else ["extra_data"]
    exec_records = await query.only(*fetch_fields).all()

    token_total = 0
    token_input = 0
    token_output = 0
    chars_total = 0
    chat_key_stats: dict[str, dict] = {}

    for record in exec_records:
        if not record.extra_data:
            continue
        try:
            extra = json.loads(record.extra_data)
            if not isinstance(extra, dict):
                continue
            t_total = extra.get("token_consumption", 0)
            t_in = extra.get("token_input", 0)
            t_out = extra.get("token_output", 0)
            c_total = extra.get("chars_count_total", 0)

            token_total += t_total
            token_input += t_in
            token_output += t_out
            chars_total += c_total

            if multi_group:
                ck = record.chat_key
                if ck not in chat_key_stats:
                    chat_key_stats[ck] = {"token_total": 0, "token_input": 0, "token_output": 0, "chars_total": 0}
                chat_key_stats[ck]["token_total"] += t_total
                chat_key_stats[ck]["token_input"] += t_in
                chat_key_stats[ck]["token_output"] += t_out
                chat_key_stats[ck]["chars_total"] += c_total
        except json.JSONDecodeError:
            pass

    result: dict = {
        "token_total": token_total,
        "token_input": token_input,
        "token_output": token_output,
        "chars_total": chars_total,
        "date": today,
        "chat_keys": chat_keys,
    }

    if multi_group and chat_key_stats:
        result["chat_key_stats"] = dict(
            sorted(chat_key_stats.items(), key=lambda x: x[1]["token_total"], reverse=True)
        )

    return result


def _scope_label(chat_keys: Optional[list[str]]) -> str:
    if not chat_keys:
        return "全局"
    if len(chat_keys) == 1:
        return chat_keys[0]
    return f"{len(chat_keys)} 个群聊"


def _build_summary(stats: dict) -> str:
    """精简摘要（k 单位，无群聊明细）"""
    if stats["token_total"] == 0 and stats["chars_total"] == 0:
        return f"今日（{stats['date']}）{_scope_label(stats['chat_keys'])} 暂无消耗记录喵~"

    lines = [
        f"📊 今日（{stats['date']}）{_scope_label(stats['chat_keys'])} AI 消耗",
        f"─────────────────────",
        f"💰 Token: {_fmt_k(stats['token_total'])}  📥 {_fmt_k(stats['token_input'])} / 📤 {_fmt_k(stats['token_output'])}",
    ]
    if stats.get("chars_total", 0) > 0:
        lines.append(f"📝 字符: {_fmt_k(stats['chars_total'])}")

    if stats.get("chat_key_stats"):
        lines.append(f"─────────────────────")
        lines.append(f"🗂 各群聊（Token）:")
        for ck, cs in stats["chat_key_stats"].items():
            lines.append(f"  {ck}  {_fmt_k(cs['token_total'])}")

    return "\n".join(lines)


def _build_detail(stats: dict) -> str:
    """详细明细模式（完整数值 + 群聊分组）"""
    if stats["token_total"] == 0 and stats["chars_total"] == 0:
        return f"今日（{stats['date']}）{_scope_label(stats['chat_keys'])} 暂无消耗记录喵~"

    lines = [
        f"📊 今日（{stats['date']}）{_scope_label(stats['chat_keys'])} AI 消耗 [详细]",
        f"═══════════════════════════════",
        f"💰 Token 总消耗: {stats['token_total']:,}",
        f"   📥 输入:     {stats['token_input']:,}",
        f"   📤 输出:     {stats['token_output']:,}",
    ]

    if stats.get("chars_total", 0) > 0:
        lines.append(f"─────────────────────────────────")
        lines.append(f"📝 字符总计: {stats['chars_total']:,}")

    if stats.get("chat_key_stats"):
        lines.append(f"─────────────────────────────────")
        lines.append(f"🗂 各群聊明细（按消耗降序）:")
        for ck, cs in stats["chat_key_stats"].items():
            chars_part = f"  📝 {cs['chars_total']:,}" if cs.get("chars_total", 0) > 0 else ""
            lines.append(
                f"  [{ck}]"
                f"\n    💰 {cs['token_total']:,}  📥 {cs['token_input']:,} / 📤 {cs['token_output']:,}{chars_part}"
            )

    return "\n".join(lines)


@plugin.mount_command(
    name="token_stats",
    description="查询当日 AI 消耗统计（默认当前群聊）",
    aliases=["ts", "字符统计", "token统计"],
    usage="ts [-all] [-detail] [-c group1,group2]",
    permission=CommandPermission.SUPER_USER,
    category="统计",
)
async def token_stats_cmd(
    context: CommandExecutionContext,
    args: str = Arg(
        "-all 全部群聊 | -detail 详细模式 | -c group1,group2 指定群聊",
        default="",
        greedy=True,
    ),
) -> CommandResponse:
    """查询当日 Token 和字符消耗统计

    默认只统计当前群聊；-all 展示全部；-c 指定群聊；-detail 显示完整数值。
    """
    show_all, detail, chat_keys = _parse_flags(args)

    if show_all:
        effective_keys = None  # 全局
    elif chat_keys:
        effective_keys = chat_keys
    else:
        effective_keys = [context.chat_key]  # 默认当前群聊

    stats = await get_token_stats_async(chat_keys=effective_keys, detail=detail)

    response_text = _build_detail(stats) if detail else _build_summary(stats)
    return CmdCtl.success(response_text)


@plugin.mount_sandbox_method(
    SandboxMethodType.TOOL,
    "获取当日 AI 消耗统计",
    description=(
        "获取当日累计的 Token 和字符消耗统计。\n"
        "Args:\n"
        "  chat_keys (list[str] | None): 要统计的群聊列表；None 表示全局，默认为 None\n"
        "  detail (bool): 是否包含各群聊详细明细，默认为 False\n"
        "Returns:\n"
        "  dict: 包含 token_total、token_input、token_output、chars_total、date 的字典。\n"
        "  当 detail=True 且多群时，额外包含 chat_key_stats（各群聊消耗明细）。"
    ),
)
async def get_token_stats_sandbox(_ctx, chat_keys: Optional[list[str]] = None, detail: bool = False) -> dict:
    """沙盒方法：获取当日 Token 和字符统计

    Args:
        chat_keys: 要统计的群聊列表；None 表示全局
        detail: 是否包含各群聊分组明细

    Returns:
        dict: 当日消耗统计信息
    """
    return await get_token_stats_async(chat_keys=chat_keys, detail=detail)
