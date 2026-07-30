"""Agent 编排层。

为避免纯逻辑模块被重依赖（langgraph/playwright）拖累，
graph/runner 采用显式导入：from agent.graph import build_graph。
"""
