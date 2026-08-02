"""动作集注册表与工厂。

对外暴露：
- ``ActionDef``：动作数据类
- ``get_actions(body_type, selected)``：按 body_type 获取动作列表（可选过滤）
- ``get_all_body_types()``：列出所有支持的 body_type
- ``get_action(body_type, name)``：按名称获取单个动作

设计取舍：
- 注册表在模块加载时即构建（4 套动作集为静态常量），O(1) 查询。
- ``get_actions`` 返回**副本列表**（``list(...)``），避免调用方意外修改全局常量；
  但列表内的 ``ActionDef`` 实例仍为共享引用——如需修改请用 ``dataclasses.replace``。
"""

from __future__ import annotations

from .base import ActionDef, snake_to_pascal
from .humanoid import HUMANOID_ACTIONS
from .limbless import LIMBLESS_ACTIONS
from .object import OBJECT_ACTIONS
from .quadruped import QUADRUPED_ACTIONS

__all__ = [
    "ActionDef",
    "snake_to_pascal",
    "get_actions",
    "get_action",
    "get_all_body_types",
    "HUMANOID_ACTIONS",
    "QUADRUPED_ACTIONS",
    "LIMBLESS_ACTIONS",
    "OBJECT_ACTIONS",
]

_ACTION_REGISTRY: dict[str, list[ActionDef]] = {
    "humanoid": HUMANOID_ACTIONS,
    "quadruped": QUADRUPED_ACTIONS,
    "limbless": LIMBLESS_ACTIONS,
    "object": OBJECT_ACTIONS,
}


def get_actions(body_type: str, selected: list[str] | None = None) -> list[ActionDef]:
    """获取指定 body_type 的动作列表。

    Args:
        body_type: 体型类别，必须是注册表中的键之一。
        selected: 可选的动作名白名单；若提供则只返回名称匹配的动作，
            并保持注册表中的原始顺序。

    Returns:
        动作列表（副本）。

    Raises:
        ValueError: body_type 未知。
    """
    if body_type not in _ACTION_REGISTRY:
        raise ValueError(
            f"Unknown body_type: {body_type}. Available: {list(_ACTION_REGISTRY.keys())}"
        )
    actions = list(_ACTION_REGISTRY[body_type])
    if selected:
        wanted = set(selected)
        actions = [a for a in actions if a.name in wanted]
    return actions


def get_action(body_type: str, name: str) -> ActionDef:
    """按名称获取单个动作。

    Raises:
        ValueError: body_type 未知或动作名不存在。
    """
    for action in get_actions(body_type):
        if action.name == name:
            return action
    raise ValueError(f"Unknown action '{name}' for body_type '{body_type}'.")


def get_all_body_types() -> list[str]:
    """返回所有支持的 body_type。"""
    return list(_ACTION_REGISTRY.keys())
