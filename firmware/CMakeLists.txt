# CIRA Device Runtime — ESP32-S3-Touch-LCD-1.85C-BOX (HW V2)
# 目标版本: v0.8.0  (硬件基线, 对应 HARDWARE.md 锁定的 V2 规格)
# 模块化架构: Device Runtime 只依赖冻结接口 (MODULE_INTERFACES.md §1.3 / §2.2)
#   模块1(CIRA Core) → respond() 返回 ResponsePackage
#   模块2(Language System) → synthesize() 返回 AudioHandle
#   本固件 = 模块3, 负责 "How to show" (状态/星云/音频/触摸/熄屏)
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(cira_device_runtime)
