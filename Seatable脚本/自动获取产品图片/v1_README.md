# 亚马逊产品图片获取脚本 V1

## 版本特点
- 基础的图片获取功能
- 单线程顺序处理
- 支持主要亚马逊站点
- 基本的错误处理

## 主要功能
1. 从亚马逊产品页面获取主图
2. 自动更新到SeaTable数据库
3. 支持基本的重试机制
4. 简单的日志输出

## 使用方法
1. 安装依赖：
```bash
pip install seatable-api requests
```

2. 配置SeaTable信息：
```python
server_url = 'https://cloud.seatable.cn'
api_token = '你的API Token'
table_name = 'Task'  # 表格名称
```

3. 运行脚本：
```bash
python get_amazon_images_v1.py
```

## 数据表要求
- 表名：Task
- 必需列：
  - 产品链接：文本类型
  - 产品图片：图片类型

## 支持的站点
- 美国 (amazon.com)
- 日本 (amazon.co.jp)
- 英国 (amazon.co.uk)
- 德国 (amazon.de)
- 法国 (amazon.fr)
- 意大利 (amazon.it)
- 西班牙 (amazon.es)

## 注意事项
1. 网络连接要求稳定
2. 处理速度较慢（每条记录约10-20秒）
3. 失败时不会自动重试
4. 日志信息较简单

## 已知限制
1. 不支持多线程
2. 错误处理机制简单
3. 无法处理复杂的重定向
4. 图片质量不一定最优

## 适用场景
- 数据量较小（建议小于500条）
- 网络环境稳定
- 无需高并发处理
- 对处理速度要求不高

## 维护建议
1. 定期检查API Token有效性
2. 监控日志输出
3. 必要时手动重试失败项
4. 建议在使用前备份数据 