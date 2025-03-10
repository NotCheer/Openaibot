# -*- coding: utf-8 -*-
# @Time    : 2023/8/16 下午8:54
# @Author  : sudoskys
# @File    : func_call.py
# @Software: PyCharm
import threading
from typing import List, Dict
from typing import Optional, Type

from . import _openapi_version_, BaseTool, get_loaded_plugins, Plugin, get_plugin
from .schema import FuncPair, Function
from ...sdk.schema import File

threading_lock = threading.Lock()


class ToolRegister(object):
    """
    扩展对 _plugins 字段的操作,需要实例化以获取数据
    """

    def __init__(self):
        self.version = _openapi_version_
        self.pair_function: Dict[str, FuncPair] = {}
        self.plugins = get_loaded_plugins()
        self.__prepare()

    def __prepare(self):
        # 遍历所有插件
        for item in self.plugins:
            for sub_item in item.metadata.function:
                self.pair_function[sub_item.name] = sub_item

    def get_tool(self, name: str) -> Optional[Type[BaseTool]]:
        if not self.pair_function.get(name, None):
            return None
        return self.pair_function[name].tool

    def get_plugin(self, name: str) -> Optional[Plugin]:
        return get_plugin(name)

    @property
    def functions(self) -> Dict[str, Function]:
        _item: Dict[str, Function] = {}
        for item in self.plugins:
            for sub_item in item.metadata.function:
                _item[sub_item.name] = sub_item.function
        return _item

    @property
    def tools(self) -> List[Type[BaseTool]]:
        _item: List[Type[BaseTool]] = []
        for item in self.plugins:
            for sub_item in item.metadata.function:
                _item.append(sub_item.tool)
        return _item

    def filter_pair(self, key_phrases: str, file_list: List[File] = None, ignore: List[str] = None) -> List[Function]:
        """
        过滤group中的函数
        """
        if ignore is None:
            ignore = []
        function_list = []
        for func_name, pair_cls in self.pair_function.items():
            _cls = pair_cls.tool()
            if _cls.func_message(message_text=key_phrases):
                # 关键词大类匹配成功
                if func_name in ignore:
                    continue  # 忽略函数
                if _cls.file_match_required:
                    if not file_list:
                        break  # 需要文件但是没有文件
                    for file in file_list:
                        if _cls.file_match_required.match(file.file_name):
                            continue  # 文件匹配成功
                    else:
                        continue  # 需要文件但是没有文件匹配成功
                function_list.append(pair_cls.function)
        return function_list
