# SeaTable 图片同步工具 V3.0

自动将 SeaTable 表格中的图片转存到图床，支持多表格、多列处理。

## 功能特点

- 支持多个Base批量处理
- 支持多表格批量处理
- 支持多图片列同步
- 自动重试机制
- 详细的日志记录
- 可配置的图床接口
- 文件大小限制
- 进度保存和恢复

## 文件说明

### 核心文件
- `src/sync.py`: 主程序文件
  - `ImageBed` 类：处理图片上传到图床
  - `SeaTableManager` 类：管理SeaTable的操作
  - `main()` 函数：程序入口，处理多个base

- `src/config.py`: 配置管理文件
  - 环境变量加载和验证
  - 日志配置
  - 多base token解析

- `src/utils.py`: 工具函数文件
  - `ProgressManager` 类：处理进度保存和恢复
  - `ImageProcessor` 类：图片处理相关工具
  - 文件操作辅助函数

- `requirements.txt`: 依赖管理文件
  ```
  seatable-api>=2.3.3
  requests>=2.31.0
  pyyaml>=6.0.1
  python-dotenv>=1.0.0
  ```

## 环境变量配置

### 必需配置（二选一）
- `SEATABLE_API_TOKENS`: 多个Base的Token配置，支持两种格式：
  1. JSON格式（推荐）：
     ```json
     [
       {"name": "base1", "token": "token1"},
       {"name": "base2", "token": "token2"}
     ]
     ```
  2. 简单格式：`token1,token2,token3`

- `SEATABLE_API_TOKEN`: 单个Base的Token（如果只需处理一个Base）

### 可选配置
- `SEATABLE_SERVER_URL`: SeaTable 服务器地址（默认: https://cloud.seatable.cn）
- `IMAGE_BED_API`: 图床上传API（默认: https://img.shuang.fun/api/tgchannel）
- `IMAGE_SIZE_LIMIT`: 图片大小限制，单位MB（默认: 5）
- `LOG_LEVEL`: 日志级别（默认: INFO）
- `LOG_FILE`: 日志文件路径（默认: logs/sync.log）
- `SAVE_PROGRESS`: 是否保存进度（默认: true）
- `PROGRESS_FILE`: 进度文件路径（默认: logs/progress.json）
- `PROGRESS_SAVE_INTERVAL`: 进度保存间隔，单位秒（默认: 300）

## 处理流程

1. 配置加载
   - 读取环境变量
   - 解析base tokens
   - 设置日志系统

2. Base处理
   - 遍历每个base
   - 获取base的表格列表
   - 处理每个表格

3. 表格处理
   - 识别图片列
   - 分页获取数据
   - 处理每行数据

4. 图片处理
   - 下载原图片
   - 验证文件大小
   - 上传到图床
   - 更新表格数据

5. 进度管理
   - 定期保存进度
   - 支持断点续传
   - 统计处理结果

## 使用方法

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 设置环境变量：
   - 在青龙面板中添加必要的环境变量
   - 设置 `SEATABLE_API_TOKENS` 或 `SEATABLE_API_TOKEN`
   - 对于多个Base，推荐使用JSON格式的 `SEATABLE_API_TOKENS`

3. 运行程序：
   ```bash
   python src/sync.py
   ```

## 日志说明

程序运行时会输出详细的日志，包括：
- `[主程序]`: 程序整体运行状态
- `[Base]`: 各个Base的处理情况
- `[表格]`: 表格处理进度
- `[行]`: 行数据处理
- `[图片]`: 图片处理状态
- `[下载]`: 图片下载进度
- `[上传]`: 图床上传状态
- `[进度]`: 进度保存信息

## 错误处理

1. Base级别错误
   - Base认证失败
   - 获取表格失败
   - 权限不足

2. 表格级别错误
   - 表格不存在
   - 无图片列
   - 数据获取失败

3. 图片处理错误
   - 下载失败
   - 大小超限
   - 上传失败
   - 格式不支持

所有错误都会被记录在日志中，并且不会影响其他数据的处理。

## 更新日志

### V3.0
- 重构项目结构
- 添加多Base支持
- 使用环境变量配置
- 改进错误处理
- 优化日志输出
- 添加进度保存功能 