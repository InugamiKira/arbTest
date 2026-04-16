#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修改后的data_fetcher.py文件，包括中间价和在岸价的获取功能
"""

import sys
import os
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from readers.data_fetcher import data_fetcher


def test_official_exchange_rate():
    """测试人民币中间价获取功能"""
    print("🔍 测试人民币中间价获取功能")
    print(f"当前日期: {datetime.now().date()}")
    print(f"当前时间: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)
    
    # 调用fetch_official_exchange_rate方法
    middle_rate_data = data_fetcher.fetch_official_exchange_rate()
    
    if middle_rate_data:
        print("✅ 成功获取人民币中间价")
        print("📊 汇率数据:")
        for key, value in middle_rate_data.items():
            print(f"  {key}: {value}")
    else:
        print("❌ 无法获取人民币中间价")


def test_cny_spot_rate():
    """测试人民币在岸价获取功能"""
    print("\n🔍 测试人民币在岸价获取功能")
    print(f"当前日期: {datetime.now().date()}")
    print(f"当前时间: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)
    
    # 调用fetch_cny_spot_rate方法
    cny_data = data_fetcher.fetch_cny_spot_rate()
    
    if cny_data:
        print("✅ 成功获取人民币在岸价")
        print("📊 汇率数据:")
        for key, value in cny_data.items():
            print(f"  {key}: {value}")
    else:
        print("❌ 无法获取人民币在岸价")


def main():
    """主函数"""
    test_official_exchange_rate()
    test_cny_spot_rate()


if __name__ == "__main__":
    main()
