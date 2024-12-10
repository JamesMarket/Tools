from seatable_api import Base, context
import requests
import os
import time
from urllib.parse import urlparse
import json
import tempfile
import asyncio
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ProcessStats:
    """处理统计数据类"""
    total_processed: int = 0
    total_success: int = 0
    total_failed: int = 0
    download_failed: int = 0
    upload_failed: int = 0
    processed_rows: int = 0
    updated_rows: int = 0

    def log_stats(self):
        """输出统计信息"""
        logger.info("\n📊 处理完成！")
        logger.info(f"总计处理行数: {self.processed_rows} 行")
        logger.info(f"更新行数: {self.updated_rows} 行")
        logger.info("\n🔍 详细统计:")
        logger.info(f"下载失败: {self.download_failed} 张")
        logger.info(f"上传失败: {self.upload_failed} 张")
        if self.total_processed > 0:
            success_rate = (self.total_success / self.total_processed * 100)
            logger.info(f"总成功率: {success_rate:.1f}% ({self.total_success}/{self.total_processed})")
        else:
            logger.info("没有需要处理的图片")

class ImageHandler:
    """图片处理���类"""
    def __init__(self, max_size: int = 5 * 1024 * 1024):
        self.max_size = max_size
        self.stats = ProcessStats()

    async def download_file(self, url: str, temp_file: str) -> bool:
        """下载文件"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            if response.status_code == 200:
                data = response.content
                if len(data) > self.max_size:
                    logger.warning(f"❌ 文件大小超过{self.max_size/1024/1024}MB限制")
                    return False
                with open(temp_file, 'wb') as f:
                    f.write(data)
                return True
            else:
                logger.error(f"❌ 下载失败，状态码: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ 下载出错: {str(e)}")
            return False

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.read()
                        if len(data) > self.max_size:
                            logger.warning(f"❌ 文件大小超过{self.max_size/1024/1024}MB限制")
                            return False
                        with open(temp_file, 'wb') as f:
                            f.write(data)
                        return True
                    else:
                        logger.error(f"❌ 下载失败，状态码: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ 下载出错: {str(e)}")
            return False

    async def upload_file(self, file_path: str) -> Optional[str]:
        """异步上传文件（需要子类实现）"""
        raise NotImplementedError

    def create_temp_file(self, ext: str = '.jpg') -> str:
        """创建临时文件"""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp_file.close()
        return temp_file.name

class CustomStorage(ImageHandler):
    """自定义图床处理类"""
    def __init__(self, upload_api: str, max_size: int = 5 * 1024 * 1024):
        super().__init__(max_size)
        self.upload_api = upload_api

    async def upload_file(self, file_path: str) -> Optional[str]:
        """异步上传文件到图床"""
        try:
            if not os.path.exists(file_path):
                return None

            file_size = os.path.getsize(file_path)
            if file_size > self.max_size:
                logger.warning(f"❌ 文件大小超过限制: {file_size / 1024 / 1024:.2f}MB")
                return None

            async with aiohttp.ClientSession() as session:
                with open(file_path, 'rb') as f:
                    form = aiohttp.FormData()
                    form.add_field('file', f)
                    async with session.post(self.upload_api, data=form) as response:
                        if response.status == 200:
                            result = await response.json()
                            if result.get('url'):
                                return result['url']
                            logger.error(f"❌ 上传失败: {result.get('message', '未知错误')}")
                        else:
                            logger.error(f"❌ 上传失败，状态码: {response.status}")
        except Exception as e:
            logger.error(f"❌ 上传出错: {str(e)}")
        return None

class SeaTableHandler:
    """SeaTable处理类"""
    def __init__(self, api_token: str, server_url: str):
        self.base = Base(api_token, server_url)
        self.base.auth()

    async def get_tables(self) -> List[Tuple[str, List]]:
        """获取所有表格"""
        try:
            metadata = self.base.get_metadata()
            tables = metadata.get('tables', [])
            return [(table['name'], table.get('columns', [])) for table in tables]
        except Exception as e:
            logger.error(f"❌ 获取表格失败: {str(e)}")
            return []

    def get_image_columns(self, columns: List) -> List[str]:
        """获取图片列"""
        return [col['name'] for col in columns if col.get('type') == 'image']

    async def list_rows(self, table_name: str, start: int, limit: int) -> List[Dict]:
        """获取表格数据"""
        try:
            return self.base.list_rows(table_name, start=start, limit=limit)
        except Exception as e:
            logger.error(f"❌ 获取行数据失败: {str(e)}")
            return []

    async def update_row(self, table_name: str, row_id: str, data: Dict) -> bool:
        """更新行数据"""
        try:
            self.base.update_row(table_name, row_id, data)
            return True
        except Exception as e:
            logger.error(f"❌ 更新行失败: {str(e)}")
            return False

class ImageProcessor:
    """图片处理器"""
    def __init__(self, api_token: str, server_url: str, upload_api: str):
        self.seatable = SeaTableHandler(api_token, server_url)
        self.storage = CustomStorage(upload_api)
        self.stats = ProcessStats()

    async def process_image(self, image_url: str) -> Optional[str]:
        """处理单个图片"""
        if not image_url or not isinstance(image_url, str):
            logger.warning(f"❌ 无效的图片URL: {image_url}")
            return None

        # 验证URL
        parsed_url = urlparse(image_url)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            logger.warning(f"❌ 无效的URL格式: {image_url}")
            return None

        # 获取扩展名
        ext = os.path.splitext(parsed_url.path)[1] or '.jpg'
        temp_file = self.storage.create_temp_file(ext)

        try:
            logger.info(f"📥 下载图片: {image_url}")
            if await self.storage.download_file(image_url, temp_file):
                logger.info("✅ 下载成功")
                logger.info(f"📤 开始上传...")
                new_url = await self.storage.upload_file(temp_file)
                if new_url:
                    logger.info(f"✅ 上传成功: {new_url}")
                    return new_url
                else:
                    self.stats.upload_failed += 1
            else:
                self.stats.download_failed += 1
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

        return None

    async def process_row(self, row: Dict, table_name: str, image_column: str) -> bool:
        """处理单行数据"""
        row_id = row['_id']
        images = row.get(image_column, [])
        if not images:
            return False

        logger.info(f"\n🔄 处理行 {row_id} 的图片...")
        
        if isinstance(images, str):
            images = [images]

        new_images = []
        updated = False

        for index, image in enumerate(images, 1):
            image_url = image.get('url', '') if isinstance(image, dict) else image
            
            if 'img.shuang.fun' in image_url:
                logger.info(f"⏩ 图片 {index} 已在图床中")
                new_images.append(image)
                continue

            self.stats.total_processed += 1
            new_url = await self.process_image(image_url)

            if new_url:
                new_images.append(new_url)
                updated = True
                self.stats.total_success += 1
            else:
                new_images.append(image)
                self.stats.total_failed += 1

            await asyncio.sleep(1)  # 避免请求过于频繁

        if updated:
            if await self.seatable.update_row(table_name, row_id, {image_column: new_images}):
                logger.info(f"✅ 行 {row_id} 更新成功")
                self.stats.updated_rows += 1
                return True

        return False

    async def process_table(self, table_name: str, image_column: str):
        """处理表格"""
        logger.info(f"\n🚀 开始处理表格 {table_name} 的 {image_column} 列")
        
        page_size = 50
        start = 0

        while True:
            rows = await self.seatable.list_rows(table_name, start, page_size)
            if not rows:
                break

            self.stats.processed_rows += len(rows)
            current_page = start // page_size + 1
            logger.info(f"\n📄 处理第 {current_page} 页，{len(rows)} 条记录")

            tasks = [self.process_row(row, table_name, image_column) for row in rows]
            await asyncio.gather(*tasks)

            start += len(rows)
            if len(rows) < page_size:
                break

        self.stats.log_stats()

async def main_async():
    """主函数"""
    server_url = context.server_url or 'https://cloud.seatable.cn'
    api_token = context.api_token or 'your_api_token'
    upload_api = 'https://img.shuang.fun/api/tgchannel'

    processor = ImageProcessor(api_token, server_url, upload_api)
    
    logger.info("🔍 获取表格信息...")
    tables = await processor.seatable.get_tables()
    if not tables:
        logger.error("❌ 未找到表格")
        return

    logger.info(f"✅ 找到 {len(tables)} 个表格")
    
    for table_name, columns in tables:
        image_columns = processor.seatable.get_image_columns(columns)
        if not image_columns:
            logger.info(f"⏩ 表格 {table_name} 无图片列")
            continue

        logger.info(f"\n📋 处理表格: {table_name}")
        logger.info(f"📊 图片列: {', '.join(image_columns)}")
        
        for column_name in image_columns:
            try:
                await processor.process_table(table_name, column_name)
            except Exception as e:
                logger.error(f"❌ 处理失败: {str(e)}")

def main():
    """程序入口"""
    logger.info("🚀 启动图片同步工具...")
    asyncio.run(main_async())
    logger.info("\n✨ 程序完成")

if __name__ == '__main__':
    main()