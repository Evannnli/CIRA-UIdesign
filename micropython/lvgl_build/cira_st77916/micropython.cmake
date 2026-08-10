# cira_st77916 USER_C_MODULE 构建注册（CMake 版）
# lv_micropython 的 CMake 构建通过 USER_C_MODULES=<本文件路径> 包含。
# 仅依赖 ESP-IDF 自带的 esp_lcd / driver / ledc，无需外部组件。

add_library(usermod_cira_st77916 INTERFACE)

target_sources(usermod_cira_st77916 INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/st77916.c
)

# st77916.c 与 st77916_init_data.h 同目录，作为 include 目录。
target_include_directories(usermod_cira_st77916 INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

# esp_cache_msync（DMA 前清 D$ 保证 PSRAM/内部 SRAM 缓存一致性）所在头文件目录。
target_include_directories(usermod_cira_st77916 INTERFACE
    $ENV{IDF_PATH}/components/esp_mm/include
)

# 链接到 MicroPython 的用户模块总目标，使其被编译进固件。
target_link_libraries(usermod INTERFACE usermod_cira_st77916)
