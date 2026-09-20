#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SAUSG MCP Server

把 .trae/skills/sausg/scripts 下的三个脚本封装为 MCP tools：
  - sausg_open    用指定模块打开 .ssg 模型
  - sausg_calc    运行结构计算（弹塑性/非线性/动力时程），完成后读取主要结果
  - sausg_result  读取已完成的计算结果

设计原则：不复制函数实现，直接 import 原 skill 脚本，保持单一事实来源。
"""

import os
import sys
import json
import asyncio
from typing import Any

# Windows 控制台编码兼容
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 把原 skill 的 scripts 目录加入 import 路径，复用现有函数实现
SCRIPTS_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..", "..", "skills", "sausg", "scripts",
    )
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# 复用 skill 里已有的实现，不重写
from sausg_open import open_sausg_model  # noqa: E402
from sausg_calc import run_sausg  # noqa: E402
from sausg_result import read_main_results, format_results  # noqa: E402

from mcp.server import Server  # noqa: E402
from mcp.types import Tool, TextContent  # noqa: E402

server = Server("sausg")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="sausg_open",
            description=(
                "用指定 SAUSG 模块打开 .ssg 模型文件。"
                "module 可选: open / sausage / delta / jg / pi / zeta，"
                "或中文 通用 / 非线性 / 钢结构 / 加固 / 隔震 / 减震。"
                "默认 OpenSAUSG。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "model_path": {
                        "type": "string",
                        "description": ".ssg 模型文件路径，相对路径会基于 cwd 解析",
                    },
                    "module": {
                        "type": "string",
                        "description": "模块名，留空默认 OpenSAUSG",
                    },
                    "sausg_dir": {
                        "type": "string",
                        "description": "SAUSG 安装目录，留空自动搜索 D 盘最新版本",
                    },
                },
                "required": ["model_path"],
            },
        ),
        Tool(
            name="sausg_calc",
            description=(
                "运行 SAUSG 结构计算（弹塑性 / 非线性 / 动力时程），"
                "完成后自动读取并返回主要结果（周期、反力、基底剪力、位移角）。"
                "禁止与正在运行的其他 SAUSG 计算并发。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "model_path": {
                        "type": "string",
                        "description": ".ssg 模型文件路径",
                    },
                    "sausg_dir": {
                        "type": "string",
                        "description": "SAUSG 安装目录，留空自动搜索",
                    },
                    "cleanup": {
                        "type": "boolean",
                        "description": "是否在计算前清理旧结果文件（.BCR/.BEM/StaticResult/...），默认 true",
                    },
                    "wait": {
                        "type": "boolean",
                        "description": "是否等待计算完成，默认 true。false 时仅启动进程后立即返回 pid",
                    },
                },
                "required": ["model_path"],
            },
        ),
        Tool(
            name="sausg_result",
            description=(
                "读取已完成 SAUSG 计算的主要结果："
                "基本周期 T1-T6、圆频率 ω、频率 f、楼层总重、底部反力、"
                "基底剪力（含剪重比）、最大层间位移角、计算报告文件名。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "model_dir": {
                        "type": "string",
                        "description": "模型所在目录路径",
                    },
                    "model_name": {
                        "type": "string",
                        "description": "模型名（不带扩展名），留空则读取目录下所有结果",
                    },
                },
                "required": ["model_dir"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "sausg_open":
            result = open_sausg_model(
                arguments["model_path"],
                arguments.get("module"),
                arguments.get("sausg_dir"),
            )
        elif name == "sausg_calc":
            result = run_sausg(
                arguments["model_path"],
                arguments.get("wait", True),
                arguments.get("sausg_dir"),
                arguments.get("cleanup", True),
            )
        elif name == "sausg_result":
            res = read_main_results(
                arguments["model_dir"],
                arguments.get("model_name"),
            )
            result = {"raw": res, "text": format_results(res)}
        else:
            result = {"status": "error", "message": f"unknown tool: {name}"}
    except Exception as e:
        result = {"status": "error", "message": f"tool '{name}' failed: {e}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def main() -> None:
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
