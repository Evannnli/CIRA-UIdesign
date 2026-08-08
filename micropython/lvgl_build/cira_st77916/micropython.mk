# cira_st77916 USER_C_MODULE 构建注册
# 由 lv_micropython 构建时通过 USER_C_MODULES 指向本目录自动包含。
# 仅依赖 ESP-IDF 自带的 esp_lcd，无需外部组件。

USERMOD_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

SRC_USERMOD += $(USERMOD_DIR)/st77916.c

# st77916_init_data.h 与 st77916.c 同目录，#include "st77916_init_data.h" 即可解析，
# 无需额外 -I。
