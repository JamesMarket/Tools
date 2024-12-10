# SeaTable 图片同步工具使用说明

## 配置文件说明

配置文件使用 YAML 格式，包含以下主要部分：

### 1. SeaTable 配置

```yaml
# SeaTable配置
server_url: 'https://cloud.seatable.cn'  # SeaTable服务器地址
api_token: ''                            # SeaTable API Token
table_name: ''                           # 要处理的表格名称
column_names: []                         # 要处理的列名列表，留空则自动检测
```

- `server_url`: SeaTable 服务器地址
  - 云服务版：https://cloud.seatable.cn
  - 私有部署版：填写您的服务器地址
- `api_token`: 从 SeaTable 获取的 API Token
- `table_name`: 要处理的表格名称
- `column_names`: 要处理的列名列表
  - 留空则自动检测图片列和富文本列
  - 可以指定多个列名：`['图片列1', '图片列2', '富文本列']`

### 2. 图床配置

```yaml
# 图床配置
upload_api: 'https://img.shuang.fun/api/tgchannel'  # 图床API地址
max_file_size: 5242880                              # 最大文件大小（字节）
```

- `upload_api`: 图床 API 地址
- `max_file_size`: 最大文件大��（字节）
  - 默认 5MB = 5 * 1024 * 1024 字节
  - 超过此大小的图片将被跳过

### 3. 处理配置

```yaml
# 处理配置
delay: 1.0              # 处理间隔（秒）
page_size: 1000         # 每页处理的数据量
concurrent: false       # 是否启用并发处理
max_retries: 3          # 最大重试次数
process_rich_text: true # 是否处理富文本
save_progress: true     # 是否保存进度
```

- `delay`: 每次处理图片的间隔时间
  - 建议值：1-3 秒
  - 值越大，处理越慢但越稳定
- `page_size`: 每次从 SeaTable 获取的数据量
  - 建议值：500-2000
  - 根据表格大小调整
- `concurrent`: 是否启用并发处理
  - 默认关闭
  - 启用可能提高速度但增加失败风险
- `max_retries`: 失败重试次数
  - 建议值：3-5
  - 包括下载和上传的重试
- `process_rich_text`: 是否处理富文本中的图片
  - 支持 Markdown 和 HTML 格式
- `save_progress`: 是否保存处理进度
  - 建议启用，支持断点续传

## 运行参数说明

程序支持以下命令行参数：

```bash
# 基本运行（使用配置文件中的设置）
python3 src/sync_images.py

# 指定配置文件路径
python3 src/sync_images.py -c /path/to/config.yaml

# 指定表格和列名（优先级高于配置文件）
python3 src/sync_images.py -t "表格名称" -cols "图片列" "富文本列"
```

## 日志说明

程序运行日志保存在 `logs/sync_images.log` 文件中，包含以下信息：

- 程序启动和结束时间
- 配置加载信息
- 处理进度和统计
- 错误和警告信息
- 详细的操作记录

## 常见问题

1. API Token 获取：
   - 在 SeaTable 中打开表格
   - 点击右上角设置图标
   - 选择 API Token
   - 生成并复制 Token

2. 处理速度优化：
   - 减小 `delay` 值
   - 增大 `page_size`
   - 启用 `concurrent`
   - 注意不要过于激进导致失败

3. 内存占用优化：
   - 减小 `page_size`
   - 确保定期清理日志
   - 监控临时文件使用

4. 错误处理：
   - 网络问题：增加 `max_retries`
   - 超时问题：增加 `delay`
   - 权限问题：检查 API Token
   - 空间问题：清理日志和临时文件

## 最佳实践

1. 首次运行：
   - 先用小数据量测试
   - 确认配置正确
   - 观察日志输出

2. 生产环境：
   - 启用 `save_progress`
   - 适当设置 `delay`
   - 定期检查日志
   - 配置定时任务

3. 大量数据处理：
   - 分批次处理
   - 适当调大 `delay`
   - 确保网络稳定
   - 监控系统资源

4. 安全建议：
   - 定期更新 API Token
   - 及时更新程序版本
   - 做好数据备份
   - 控制访问权限 