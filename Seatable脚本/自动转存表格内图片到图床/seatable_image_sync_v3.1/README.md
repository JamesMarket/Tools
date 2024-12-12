# SeaTable图片同步工具

这是一个用于自动将SeaTable表格中的图片同步到图床的工具。

## 功能特点

- 支持多个SeaTable base的批量处理
- 自动识别和处理图片列
- 自动跳过已经在图床中的图片
- 详细的处理日志和统计报告
- 支持青龙面板通知

## 环境要求

- Python 3.6+
- seatable_api
- requests

## 安装依赖

```bash
pip install seatable_api requests
```

## 配置说明

### 环境变量配置

1. **必需配置**

- `SEATABLE_API_TOKENS`: SeaTable API令牌配置，支持两种格式：
  ```bash
  # 格式1：指定base名称（推荐）
  export SEATABLE_API_TOKENS='base名称1:token1,base名称2:token2'
  
  # 格式2：仅指定token
  export SEATABLE_API_TOKENS='token1,token2'
  ```

2. **可选配置**

- `SEATABLE_SERVER_URL`: SeaTable服务器地址
  ```bash
  export SEATABLE_SERVER_URL='https://cloud.seatable.cn'  # 默认值
  ```

- `IMAGE_BED_API`: 图床API地址
  ```bash
  export IMAGE_BED_API='https://img.shuang.fun/api/tgchannel'  # 默认值
  ```

- `IMAGE_SIZE_LIMIT`: 图片大小限制（MB）
  ```bash
  export IMAGE_SIZE_LIMIT='5'  # 默认值
  ```

## 使用说明

1. **基本使用**
   ```bash
   python seatable_image_sync_v3.1.py
   ```

2. **在青龙面板中使用**
   - 将脚本添加到青龙面板
   - 配置必要的环境变量
   - 设置定时任务

## 工作流程

1. 初始化环境和配置
2. 连接到每个SeaTable base
3. 扫描所有表格中的图片列
4. 处理每个图片：
   - 检查是否已在图床中
   - 下载原始图片
   - 上传到图床
   - 更新表格中的图片链接
5. 生成处理报告

## 统计报告

程序执行完成后会生成详细的统计报告，包括：
```
执行完成报告
==================================================
总计处理Base数: X
总计处理表格数: X
总计处理图片数: X
总计成功转存: X
总计跳过图片: X
总计失败图片: X
执行时间: X.XX秒

详细统计：

Base: base_name
  表格: table_name
    列: column_name
      - 处理图片: X 张
      - 成功转存: X 张
      - 跳过图片: X 张
      - 失败图片: X 张
```

## 注意事项

1. 图片大小限制默认为5MB
2. 名为"产品图片"的列会被自动跳过
3. 已经在图床（img.shuang.fun）中的图片会被跳过
4. 程序会自动清理临时文件

## 日志说明

- 日志文件位置：`/ql/log/seatable_image_sync/`
- 统计文件位置：`/ql/scripts/.stats/seatable_image_sync_stats.json`
- 临时文件目录：`/ql/scripts/.temp/`

## 错误处理

- 单个图片处理失败不会影响其他图片的处理
- 单个表格处理失败不会影响其他表格的处理
- 所有错误都会被记录在日志中

## 版本历史

### v3.1
- 优化base名称处理
- 支持name:token配置格式
- 改进统计报告格式
- 添加详细的错误日志

## 贡献指南

如果您想贡献代码或报告问题，请：
1. Fork 项目
2. 创建您的特性分支
3. 提交您的更改
4. 推送到分支
5. 创建新的Pull Request

## 许可证

[MIT License](LICENSE) 