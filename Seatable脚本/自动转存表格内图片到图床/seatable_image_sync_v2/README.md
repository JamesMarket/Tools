# SeaTable 图片同步工具（青龙面板版）

这是一个用于自动将 SeaTable 中的图片同步到图床的工具，专门适配了青龙面板运行环境。

## 项目结构

```
seatable_image_sync_ql/
├── src/                    # 源代码目录
│   └── sync_images.py      # 主程序
├── logs/                   # 日志目录
│   └── sync_images.log    # 运行日志
└── requirements.txt        # 依赖包列表
```

## 功能特点

- 支持图片列和富文本列的图片处理
- 支持多表格批量处理
- 自动检测可处理的列
- 支持断点续传
- 详细的处理进度显示
- 完整的错误处理和日志记录
- 支持自定义过滤条件
- 支持并发处理（可选）

## 环境变量配置

在青龙面板中添加以下环境变量：

### 必需的环境变量

```bash
# SeaTable基础配置
SEATABLE_SERVER_URL=https://cloud.seatable.cn
SEATABLE_API_TOKEN=your-api-token

# 多表格配置（使用分号分隔表格，冒号分隔表格名和列名，逗号分隔多个列名）
SEATABLE_TABLES=表格1:图片列1,富文本列1;表格2:图片列2;表格3
```

### 可选的环境变量

```bash
# 图床配置
UPLOAD_API=https://img.shuang.fun/api/tgchannel
MAX_FILE_SIZE=5242880

# 处理配置
PROCESS_DELAY=1.0
PAGE_SIZE=1000
ENABLE_CONCURRENT=false
MAX_RETRIES=3
PROCESS_RICH_TEXT=true
SAVE_PROGRESS=true
```

### 多表格配置说明

SEATABLE_TABLES 支持以下格式：

1. 完整指定列名：`表格1:图片列1,富文本列1`
2. 单列处理：`表格2:图片列2`
3. 自动检测列：`表格3`（不加冒号和列名）

示例：
```bash
# 示例1：处理多个表格的指定列
SEATABLE_TABLES=产品表:产品图片,详情描述;文章表:封面图,正文内容

# 示例2：混合配置（指定列和自动检测）
SEATABLE_TABLES=产品表:产品图片;博客表;用户表:头像

# 示例3：全部自动检测
SEATABLE_TABLES=产品表;博客表;用户表
```

## 安装步骤

1. 在青龙面板创建目录：
```bash
mkdir -p /ql/scripts/seatable_image_sync
```

2. 上传文件到青龙面板：
```bash
cd /ql/scripts/seatable_image_sync
# 上传项目文件
```

3. 安装依赖：
```bash
pip3 install -r requirements.txt
```

4. 添加环境变量：
- 在青龙面板中点击"环境变量"
- 添加必需的环境变量
- 根据需要添加可选的环境变量

## 使用方法

1. 基本运行：
```bash
python3 src/sync_images.py
```

## 注意事项

1. 运行环境要求：
   - Python 3.6+
   - 足够的磁盘空间
   - 网络可访问 SeaTable 和图床服务

2. 性能建议：
   - 根据服务器配置调整 PROCESS_DELAY
   - 适当设置 PAGE_SIZE
   - 需要更快处理时可启用 ENABLE_CONCURRENT

3. 安全建议：
   - 妥善保管 API Token
   - 定期检查日志文件大小
   - 建议启用 SAVE_PROGRESS

## 更新日志

### v2.2
- 添加多表格处理支持
- 优化环境变量配置
- 增加断点续传功能
- 改进日志记录
- 添加并发处理选项

## 问题反馈

如有问题或建议，请提交 Issue。 