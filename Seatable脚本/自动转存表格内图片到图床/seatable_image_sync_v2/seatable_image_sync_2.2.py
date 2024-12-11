from seatable_api import Base, context
import requests
import os
import time
from urllib.parse import urlparse
import json
import tempfile
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('image_sync.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

def create_session():
    """创建带有重试机制的会话"""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,  # 最大重试次数
        backoff_factor=1,  # 重试间隔
        status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的HTTP状态码
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

class CustomStorage:
    def __init__(self, upload_api):
        self.upload_api = upload_api
        self.session = create_session()

    def upload_to_custom_storage(self, temp_file_path):
        """上传图片到自定义图床"""
        try:
            # 检查文件大小
            file_size = os.path.getsize(temp_file_path)
            if file_size > 5 * 1024 * 1024:  # 5MB
                logger.warning(f"文件大小超过5MB限制: {file_size / 1024 / 1024:.2f}MB")
                return None
            
            files = {'file': open(temp_file_path, 'rb')}
            logger.info(f"正在上传图片到: {self.upload_api}")
            
            response = self.session.post(
                self.upload_api,
                files=files,
                timeout=60  # 增加超时时间到60秒
            )
            files['file'].close()
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get('url'):
                        return result.get('url')
                    logger.error(f"上传失败: {result.get('message', '未知错误')}")
                except json.JSONDecodeError as e:
                    logger.error(f"解析响应JSON失败: {str(e)}")
            else:
                logger.error(f"上传失败: HTTP状态码 {response.status_code}")
            return None
                
        except Exception as e:
            logger.error(f"上传过程发生错误: {str(e)}")
            return None

class ImageProcessor:
    def __init__(self, api_token, server_url, upload_api):
        self.base = Base(api_token, server_url)
        self.base.auth()
        self.storage = CustomStorage(upload_api)
        self.session = create_session()
        
    def get_file_url(self, image_url):
        """从图片URL中提取文件URL"""
        try:
            if '/workspace/' in image_url:
                # 工作区URL格式
                parts = image_url.split('/')
                if 'asset' in parts:
                    asset_index = parts.index('asset')
                    if len(parts) > asset_index + 1:
                        return '/'.join(parts[asset_index:])
            elif '/files/' in image_url:
                # API URL格式
                parts = image_url.split('/')
                if 'files' in parts:
                    files_index = parts.index('files')
                    if len(parts) > files_index + 1:
                        return '/'.join(parts[files_index:])
            return image_url
        except Exception as e:
            logger.error(f"提取文件URL失败: {str(e)}")
            return image_url

    def get_file_info(self, image_url):
        """从图片URL中提取文件信息"""
        try:
            if '/workspace/' in image_url:
                # 示例URL: https://cloud.seatable.cn/workspace/335985/asset/c2f64bb5-7ffe-4296-9af4-916ccbc52215/images/2024-12/2Z%20(4).jpg
                parts = image_url.split('/')
                if 'asset' in parts:
                    asset_index = parts.index('asset')
                    if len(parts) > asset_index + 1:
                        dtable_uuid = parts[asset_index + 1]
                        file_path = '/'.join(parts[asset_index + 2:])
                        return dtable_uuid, file_path
            return None, None
        except Exception as e:
            logger.error(f"提取文件信息失败: {str(e)}")
            return None, None

    def get_file_path(self, image_url):
        """从图片URL中提取文件路径"""
        try:
            if '/workspace/' in image_url:
                # 示例URL: https://cloud.seatable.cn/workspace/335985/asset/c2f64bb5-7ffe-4296-9af4-916ccbc52215/images/2024-12/2Z%20(4).jpg
                parts = image_url.split('/')
                if 'asset' in parts:
                    asset_index = parts.index('asset')
                    if len(parts) > asset_index + 2:
                        # 获取dtable_uuid和文件路径
                        dtable_uuid = parts[asset_index + 1]
                        file_path = '/'.join(parts[asset_index + 2:])
                        # 组合完整路径
                        return f"{dtable_uuid}/{file_path}"
            return None
        except Exception as e:
            logger.error(f"提取文件路径失败: {str(e)}")
            return None

    def download_with_retry(self, image_url, save_path, max_retries=3):
        """带重试机制的下载函数"""
        for attempt in range(max_retries):
            try:
                logger.info(f"[下载] 第 {attempt + 1}/{max_retries} 次尝试")
                self.base.download_file(image_url, save_path)
                return True
            except Exception as e:
                if "url invalid" in str(e):
                    logger.error(f"[下载] ❌ URL无效，跳过重试: {str(e)}")
                    return False
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5  # 递增等待时间
                    logger.warning(f"[下载] ⚠️ 下载失败，{wait_time}秒后重试: {str(e)}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"[下载] ❌ 下载失败，已达到最大重试次数: {str(e)}")
                    return False
        return False

    def download_image(self, image_url):
        """下载图片"""
        try:
            # 创建临时文件
            ext = os.path.splitext(urlparse(image_url).path)[1] or '.jpg'
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            temp_file.close()
            
            logger.info(f"\n[图片] 开始处理新图片")
            logger.info(f"[图片] 📥 源地址: {image_url}")
            
            try:
                # 使用重试机制下载文件
                if self.download_with_retry(image_url, temp_file.name):
                    # 检查文件是否下载成功
                    if os.path.exists(temp_file.name):
                        file_size = os.path.getsize(temp_file.name)
                        if file_size > 5 * 1024 * 1024:  # 5MB
                            logger.warning(f"[图片] ⚠️ 文件大小超过5MB限制: {file_size / 1024 / 1024:.2f}MB")
                            os.unlink(temp_file.name)
                            return None
                        if file_size > 0:
                            logger.info(f"[图片] ✅ 下载成功: {os.path.basename(image_url)} ({file_size / 1024:.2f}KB)")
                            return temp_file.name
                        else:
                            logger.error("[图片] ❌ 下载失败: 文件大小为0")
                            os.unlink(temp_file.name)
                    else:
                        logger.error("[图片] ❌ 下载失败: 文件不存在")
                else:
                    logger.error("[图片] ❌ 下载失败: 重试次数已用完")
            except Exception as e:
                logger.error(f"[图片] ❌ 下载过程出错: {str(e)}")
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
            
            return None
            
        except Exception as e:
            logger.error(f"[图片] ❌ 处理过程出错: {str(e)}")
            return None

    def process_table_images(self, table_name, image_column_name):
        """处理表格的图片"""
        logger.info(f"\n[表格] 📊 开始处理表格 {table_name} 的 {image_column_name} 列")
        
        stats = {
            'processed_rows': 0,
            'total_images': 0,
            'success_count': 0,
            'updated_rows': 0
        }
        
        page_size = 1000
        start = 0
        
        while True:
            try:
                rows = self.base.list_rows(table_name, start=start, limit=page_size)
                if not rows:
                    break
                    
                logger.info(f"\n[表格] 📄 处理第 {start // page_size + 1} 页数据，本页 {len(rows)} 条记录")
                
                for row in rows:
                    stats['processed_rows'] += 1
                    row_id = row['_id']
                    images = row.get(image_column_name, [])
                    
                    if not images:
                        continue
                        
                    if isinstance(images, str):
                        images = [images]
                    
                    new_images = []
                    updated = False
                    
                    logger.info(f"\n[行] 📝 处理行 {row_id}")
                    logger.info(f"[行] 发现 {len(images)} 张图片")
                    
                    for index, image in enumerate(images, 1):
                        image_url = image.get('url', '') if isinstance(image, dict) else image
                        
                        if not image_url:
                            logger.warning(f"[行] ⚠️ 第 {index} 张图片URL为空，跳过")
                            new_images.append(image)
                            continue
                            
                        if 'img.shuang.fun' in image_url:
                            logger.info(f"[行] ⏩ 第 {index} 张图片已在图床中，跳过")
                            new_images.append(image)
                            continue
                        
                        stats['total_images'] += 1
                        
                        temp_file_path = self.download_image(image_url)
                        if not temp_file_path:
                            new_images.append(image)
                            continue
                        
                        logger.info(f"[上传] 📤 正在上传到图床: {self.storage.upload_api}")
                        new_url = self.storage.upload_to_custom_storage(temp_file_path)
                        if new_url:
                            new_images.append(new_url)
                            updated = True
                            stats['success_count'] += 1
                            logger.info(f"[上传] ✅ 转存成功: {new_url}")
                        else:
                            logger.error("[上传] ❌ 转存失败，保留原图片")
                            new_images.append(image)
                        
                        if os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)
                        
                        time.sleep(1)
                    
                    if updated:
                        try:
                            self.base.update_row(table_name, row_id, {image_column_name: new_images})
                            logger.info(f"[行] ✅ 更新成功")
                            stats['updated_rows'] += 1
                        except Exception as e:
                            logger.error(f"[行] ❌ 更新失败: {str(e)}")
                
                start += len(rows)
                if len(rows) < page_size:
                    break
                    
            except Exception as e:
                logger.error(f"[表格] ❌ 处理页面数据时出错: {str(e)}")
                time.sleep(5)  # 出错后等待5秒再重试
                continue
        
        logger.info(f"\n[统计] 📊 处理完成！")
        logger.info(f"[统计] 总计处理行数: {stats['processed_rows']} 行")
        logger.info(f"[统计] 包含图片的行数: {stats['updated_rows']} 行")
        logger.info(f"[统计] 总计处理图片: {stats['total_images']} 张")
        logger.info(f"[统计] 成功转存: {stats['success_count']} 张")
        logger.info(f"[统计] 失败: {stats['total_images'] - stats['success_count']} 张")

def main():
    # 从环境变量获取配置
    server_url = os.getenv('SEATABLE_SERVER_URL') or context.server_url or 'https://cloud.seatable.cn'
    api_token = os.getenv('SEATABLE_API_TOKEN') or context.api_token
    upload_api = 'https://img.shuang.fun/api/tgchannel'
    
    if not api_token:
        logger.error("未提供API Token，请设置环境变量 SEATABLE_API_TOKEN 或直接在代码中配置")
        return
    
    processor = ImageProcessor(api_token, server_url, upload_api)
    
    try:
        # 获取表格信息
        metadata = processor.base.get_metadata()
        tables = metadata.get('tables', [])
        
        if not tables:
            logger.error("未找到任何表格，请检查权限和连接状态")
            return
        
        logger.info(f"发现 {len(tables)} 个表格，开始处理...")
        
        # 遍历所有表格
        for table in tables:
            table_name = table['name']
            # 获取所有图片类型的列
            image_columns = [col['name'] for col in table.get('columns', []) if col.get('type') == 'image']
            
            if not image_columns:
                logger.info(f"表格 {table_name} 中没有图片列，跳过")
                continue
                
            logger.info(f"处理表格: {table_name}")
            logger.info(f"发现图片列: {', '.join(image_columns)}")
            
            # 处理每个图片列
            for column_name in image_columns:
                logger.info(f"开始处理列: {column_name}")
                processor.process_table_images(table_name, column_name)
                
    except Exception as e:
        logger.error(f"处理过程发生错误: {str(e)}")
        return

if __name__ == '__main__':
    main() 