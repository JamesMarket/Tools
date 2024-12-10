from seatable_api import Base, context
import requests
import os
import time
from urllib.parse import urlparse
import json
import tempfile
import re
from datetime import datetime
from typing import List, Dict, Optional, Union
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Config:
    """配置类"""
    def __init__(self):
        self.upload_api = 'https://img.shuang.fun/api/tgchannel'
        self.max_file_size = 5 * 1024 * 1024  # 5MB
        self.delay = 1.0  # 处理间隔（秒）
        self.page_size = 1000  # 分页大小
        self.concurrent = False  # 是否启用并发处理
        self.max_retries = 3  # 最大重试次数
        self.process_rich_text = True  # 是否处理富文本
        self.save_progress = True  # 是否保存进度
        self.filter_condition = None  # 自定义过滤条件

class ProcessState:
    """处理状态类"""
    def __init__(self):
        self.total_processed = 0
        self.total_success = 0
        self.total_failed = 0
        self.download_failed = 0
        self.upload_failed = 0
        self.processed_rows = 0
        self.updated_rows = 0
        self.start_time = datetime.now()
        
    def get_progress(self) -> Dict:
        """获取进度信息"""
        duration = (datetime.now() - self.start_time).total_seconds()
        return {
            'total_processed': self.total_processed,
            'total_success': self.total_success,
            'total_failed': self.total_failed,
            'download_failed': self.download_failed,
            'upload_failed': self.upload_failed,
            'processed_rows': self.processed_rows,
            'updated_rows': self.updated_rows,
            'duration': duration,
            'speed': self.total_processed / duration if duration > 0 else 0
        }
        
    def print_progress(self):
        """打印进度信息"""
        progress = self.get_progress()
        logger.info("\n📊 处理进度")
        logger.info(f"总计处理行数: {progress['processed_rows']} 行")
        logger.info(f"更新行数: {progress['updated_rows']} 行")
        logger.info(f"处理图片: {progress['total_processed']} 张")
        logger.info(f"成功: {progress['total_success']} 张")
        logger.info(f"失败: {progress['total_failed']} 张")
        logger.info(f"���载失败: {progress['download_failed']} 张")
        logger.info(f"上传失败: {progress['upload_failed']} 张")
        logger.info(f"处理时间: {progress['duration']:.1f} 秒")
        logger.info(f"处理速度: {progress['speed']:.1f} 张/秒")

class CustomStorage:
    """自定义图床处理类"""
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        
    def upload_to_custom_storage(self, temp_file_path: str) -> Optional[str]:
        """上传图片到自定义图床"""
        retries = 0
        while retries < self.config.max_retries:
            try:
                # 检查文件大小
                file_size = os.path.getsize(temp_file_path)
                if file_size > self.config.max_file_size:
                    logger.warning(f"文件大小超过限制: {file_size / 1024 / 1024:.2f}MB")
                    return None
                
                # 直接使用下载的文件
                with open(temp_file_path, 'rb') as f:
                    files = {'file': f}
                    logger.info(f"正在发送请求到: {self.config.upload_api}")
                    
                    # 发送上传请求
                    response = self.session.post(
                        self.config.upload_api,
                        files=files,
                        timeout=30
                    )
                
                logger.info(f"服务器状态码: {response.status_code}")
                logger.debug(f"服务器响应内容: {response.text}")
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        if result.get('url'):
                            return result.get('url')
                        else:
                            error_msg = result.get('message', '未知错误')
                            logger.error(f"上传失败: {error_msg}")
                    except json.JSONDecodeError as e:
                        logger.error(f"解析响应JSON失败: {str(e)}")
                else:
                    logger.error(f"上传失败: HTTP状态码 {response.status_code}")
                    
                retries += 1
                if retries < self.config.max_retries:
                    time.sleep(1)  # 重试前等待
                    
            except Exception as e:
                logger.error(f"上传过程发生错误: {str(e)}")
                retries += 1
                if retries < self.config.max_retries:
                    time.sleep(1)
                    
        return None

class ImageProcessor:
    """图片处理器"""
    def __init__(self, base: Base, config: Config):
        self.base = base
        self.config = config
        self.storage = CustomStorage(config)
        self.state = ProcessState()
        
    def extract_image_urls(self, content: Union[str, Dict, List]) -> List[str]:
        """从内容中提取图片URL"""
        urls = []
        
        if isinstance(content, str):
            # 处理富文本内容
            if self.config.process_rich_text:
                # 使用正则表达式匹配图片URL
                pattern = r'!\[.*?\]\((.*?)\)|<img.*?src=[\'"](.*?)[\'"]'
                matches = re.finditer(pattern, content)
                for match in matches:
                    url = match.group(1) or match.group(2)
                    if url:
                        urls.append(url)
        elif isinstance(content, dict):
            # 处理图片字典
            url = content.get('url', '')
            if url:
                urls.append(url)
        elif isinstance(content, list):
            # 处理图片列表
            for item in content:
                urls.extend(self.extract_image_urls(item))
                
        return urls
        
    def download_image(self, image_url: str) -> Optional[str]:
        """下载图片"""
        retries = 0
        while retries < self.config.max_retries:
            try:
                # 从URL获取文件扩展名
                ext = os.path.splitext(urlparse(image_url).path)[1]
                if not ext:
                    ext = '.jpg'  # 默认扩展名
                
                # 创建临时文件，保留扩展名
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                temp_file.close()
                
                # 使用SeaTable API下载文件到临时文件
                logger.info(f"下载图片: {image_url}")
                self.base.download_file(image_url, temp_file.name)
                
                # 检查文件是否下载成功和大小限制
                if os.path.exists(temp_file.name):
                    file_size = os.path.getsize(temp_file.name)
                    if file_size > self.config.max_file_size:
                        logger.warning(f"文件大小超过限制: {file_size / 1024 / 1024:.2f}MB")
                        os.unlink(temp_file.name)
                        return None
                    if file_size > 0:
                        return temp_file.name
                
                logger.error(f"下载图片失败")
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                    
                retries += 1
                if retries < self.config.max_retries:
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"下载图片失败: {str(e)}")
                if 'temp_file' in locals() and os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                retries += 1
                if retries < self.config.max_retries:
                    time.sleep(1)
                    
        return None

    def process_table_images(self, table_name: str, column_name: str):
        """处理表格的图片"""
        logger.info(f"开始处理表格 {table_name} 中的 {column_name} 列...")
        
        # 获取进度记录
        progress_row = None
        if self.config.save_progress:
            progress_rows = self.base.filter_rows(table_name, f"进度记录_{column_name}", {})
            if progress_rows:
                progress_row = progress_rows[0]
                start = progress_row.get('已处理行数', 0)
                logger.info(f"从上次进度继续：已处理 {start} 行")
            else:
                start = 0
        else:
            start = 0
        
        while True:
            # 获取当前页的数据
            rows = self.base.list_rows(table_name, start=start, limit=self.config.page_size)
            if not rows:
                break
            
            current_page = start // self.config.page_size + 1
            logger.info(f"\n📄 处理第 {current_page} 页数据，本页 {len(rows)} 条记录")
            
            for row in rows:
                self.state.processed_rows += 1
                row_id = row['_id']
                
                # 应用过滤条件
                if self.config.filter_condition and not self.config.filter_condition(row):
                    continue
                    
                content = row.get(column_name)
                if not content:
                    continue
                
                # 提取图片URL
                image_urls = self.extract_image_urls(content)
                if not image_urls:
                    continue
                    
                new_content = content
                updated = False
                
                logger.info(f"处理行 {row_id} 的图片... (已处理 {self.state.processed_rows} 行)")
                
                for index, image_url in enumerate(image_urls, 1):
                    # 只处理 SeaTable 的图片
                    if not 'seatable.cn' in image_url:
                        logger.info(f"图片 {index} 不是SeaTable图片，跳过")
                        continue
                        
                    if 'img.shuang.fun' in image_url:
                        logger.info(f"图片 {index} 已经在图床中，跳过")
                        continue
                    
                    self.state.total_processed += 1
                    
                    # 下载原图片
                    temp_file_path = self.download_image(image_url)
                    if not temp_file_path:
                        logger.error(f"图片 {index} 下载失败，保持原链接")
                        self.state.download_failed += 1
                        self.state.total_failed += 1
                        continue
                    
                    # 上传到图床
                    logger.info(f"上传图片 {index} 到自定义图床...")
                    new_url = self.storage.upload_to_custom_storage(temp_file_path)
                    if new_url:
                        # 替换内容中的图片URL
                        new_content = new_content.replace(image_url, new_url)
                        updated = True
                        self.state.total_success += 1
                        logger.info(f"图片 {index} 已成功转存: {new_url}")
                    else:
                        logger.error(f"图片 {index} 上传失败，保持原链接")
                        self.state.upload_failed += 1
                        self.state.total_failed += 1
                    
                    # 删除临时文件
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                    
                    # 处理间隔
                    time.sleep(self.config.delay)
                
                if updated:
                    # 更新行数据
                    try:
                        self.base.update_row(
                            table_name,
                            row_id,
                            {column_name: new_content}
                        )
                        logger.info(f"行 {row_id} 更新成功")
                        self.state.updated_rows += 1
                    except Exception as e:
                        logger.error(f"更新行 {row_id} 失败: {str(e)}")
                
                # 保存进度
                if self.config.save_progress and self.state.processed_rows % 10 == 0:
                    self.save_progress(table_name, column_name, progress_row)
            
            # 更新起始位置
            start += len(rows)
            if len(rows) < self.config.page_size:
                break
        
        # 保存最终进度
        if self.config.save_progress:
            self.save_progress(table_name, column_name, progress_row)
        
        # 打印统计信息
        self.state.print_progress()
        
    def save_progress(self, table_name: str, column_name: str, progress_row: Optional[Dict]):
        """保存处理进度"""
        progress_data = {
            '列名': column_name,
            '已处理行数': self.state.processed_rows,
            '更新时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            '处理状态': self.state.get_progress()
        }
        
        try:
            if progress_row:
                self.base.update_row(table_name, progress_row['_id'], progress_data)
            else:
                self.base.append_row(f"进度记录_{column_name}", progress_data)
        except Exception as e:
            logger.error(f"保存进度失败: {str(e)}")

def main():
    # 使用SeaTable脚本环境的base对象
    server_url = context.server_url
    api_token = context.api_token
    base = Base(api_token, server_url)
    base.auth()
    
    # 创建配置
    config = Config()
    
    # 获取当前表格名称
    table_name = context.current_table
    if not table_name:
        logger.error("无法获取当前表格名称")
        return
        
    # 获取表格的列信息
    try:
        metadata = base.get_metadata()
        for table in metadata.get('tables', []):
            if table['name'] == table_name:
                # 获取图片列和富文本列
                image_columns = []
                for col in table.get('columns', []):
                    if col.get('type') == 'image':
                        image_columns.append(col['name'])
                    elif config.process_rich_text and col.get('type') == 'long text':
                        image_columns.append(col['name'])
                
                if not image_columns:
                    logger.error(f"表格 {table_name} 中没有可处理的列")
                    return
                    
                logger.info(f"发现可处理的列: {', '.join(image_columns)}")
                
                # 处理每个列
                processor = ImageProcessor(base, config)
                for column_name in image_columns:
                    logger.info(f"\n开始处理列: {column_name}")
                    processor.process_table_images(table_name, column_name)
                return
                
        logger.error(f"未找到表格: {table_name}")
    except Exception as e:
        logger.error(f"获取表格信息失败: {str(e)}")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n程序被用户中断")
    except Exception as e:
        logger.error(f"程序出错: {str(e)}")
    finally:
        logger.info("\n程序结束") 