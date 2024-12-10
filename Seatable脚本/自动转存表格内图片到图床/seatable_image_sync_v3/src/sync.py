import os
import time
import tempfile
import logging
from typing import Dict, List, Any, Optional
from seatable_api import Base
import requests

from config import Config
from utils import ProgressManager, ImageProcessor

logger = logging.getLogger(__name__)

class ImageBed:
    """图床管理器"""
    def __init__(self, upload_api: str, size_limit_mb: int = 5):
        self.upload_api = upload_api
        self.size_limit = size_limit_mb * 1024 * 1024  # 转换为字节
        self.session = requests.Session()

    def upload_image(self, file_path: str) -> Optional[str]:
        """上传图片到图床"""
        try:
            # 检查文件大小
            file_size = os.path.getsize(file_path)
            if file_size > self.size_limit:
                logger.warning(f"[上传] ⚠️ 文件大小超过限制: {ImageProcessor.format_file_size(file_size)}")
                return None

            # 上传文件
            with open(file_path, 'rb') as f:
                files = {'file': f}
                logger.info(f"[上传] 📤 正在上传到图床: {self.upload_api}")
                response = self.session.post(self.upload_api, files=files, timeout=60)

            if response.status_code == 200:
                result = response.json()
                if url := result.get('url'):
                    logger.info(f"[上传] ✅ 上传成功: {url}")
                    return url
                logger.error(f"[上传] ❌ 上传失败: {result.get('message', '未知错误')}")
            else:
                logger.error(f"[上传] ❌ 上传失败，状态码: {response.status_code}")

        except Exception as e:
            logger.error(f"[上传] ❌ 上传过程出错: {str(e)}")

        return None

class SeaTableManager:
    """SeaTable管理器"""
    def __init__(self, config: Config, api_token: str):
        self.config = config
        self.api_token = api_token
        self.base = self._init_base()
        self.image_bed = ImageBed(**config.image_bed_config)
        self.progress = ProgressManager(**config.progress_config) if config.get('progress', 'save_enabled') else None

    def _init_base(self) -> Base:
        """初始化SeaTable连接"""
        seatable_config = self.config.seatable_config
        base = Base(self.api_token, seatable_config['server_url'])
        base.auth()
        return base

    def _download_image(self, image_url: str) -> Optional[str]:
        """下载图片"""
        try:
            # 创建临时文件
            ext = ImageProcessor.get_file_extension(image_url)
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            temp_file.close()

            logger.info(f"[下载] 📥 开始下载: {image_url}")

            try:
                self.base.download_file(image_url, temp_file.name)
                file_size = os.path.getsize(temp_file.name)
                if file_size > 0:
                    logger.info(f"[下载] ✅ 下载成功: {ImageProcessor.format_file_size(file_size)}")
                    return temp_file.name
                else:
                    logger.error("[下载] ❌ 下载失败: 文件大小为0")
            except Exception as e:
                logger.error(f"[下载] ❌ 下载失败: {str(e)}")

            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            return None

        except Exception as e:
            logger.error(f"[下载] ❌ 下载过程出错: {str(e)}")
            return None

    def process_image(self, image_url: str) -> Optional[str]:
        """处理单个图片"""
        if not ImageProcessor.is_valid_image_url(image_url):
            logger.warning(f"[图片] ⚠️ 无效的图片URL: {image_url}")
            return None

        # 下载图片
        temp_file = self._download_image(image_url)
        if not temp_file:
            return None

        try:
            # 上传到图床
            new_url = self.image_bed.upload_image(temp_file)
            return new_url
        finally:
            # 清理临时文件
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def process_table(self, table_name: str) -> None:
        """处理单个表格"""
        logger.info(f"\n[表格] 📊 开始处理表格: {table_name}")
        
        try:
            # 获取表格信息
            metadata = self.base.get_metadata()
            table = next((t for t in metadata.get('tables', []) if t['name'] == table_name), None)
            if not table:
                logger.error(f"[表格] ❌ 表格不存在: {table_name}")
                return

            # 获取图片列
            image_columns = [col['name'] for col in table.get('columns', []) if col.get('type') == 'image']
            if not image_columns:
                logger.info(f"[表格] ℹ️ 表���中没有图片列，跳过")
                return

            logger.info(f"[表格] 📷 发现图片列: {', '.join(image_columns)}")

            # 处理每个图片列
            for column_name in image_columns:
                self.process_column(table_name, column_name)

        except Exception as e:
            logger.error(f"[表格] ❌ 处理表格时出错: {str(e)}")

    def process_column(self, table_name: str, column_name: str) -> None:
        """处理单个列"""
        logger.info(f"\n[列] 📑 开始处理列: {column_name}")

        stats = {
            'processed_rows': 0,
            'total_images': 0,
            'success_count': 0,
            'updated_rows': 0
        }

        try:
            # 分页处理
            page_size = 1000
            start = 0

            while True:
                # 获取当前页数据
                rows = self.base.list_rows(table_name, start=start, limit=page_size)
                if not rows:
                    break

                logger.info(f"[列] 📄 处理第 {start // page_size + 1} 页，{len(rows)} 条记录")

                # 处理每一行
                for row in rows:
                    stats['processed_rows'] += 1
                    self.process_row(table_name, column_name, row, stats)

                # 更新进度
                if self.progress:
                    self.progress.update_table_progress(table_name, {
                        'last_processed_row': start + len(rows),
                        'stats': stats
                    })

                start += len(rows)
                if len(rows) < page_size:
                    break

            # 输出统计信息
            logger.info(f"\n[统计] 📊 列 {column_name} 处理完成")
            logger.info(f"[统计] 总计处理行数: {stats['processed_rows']} 行")
            logger.info(f"[统计] 包含图片的行数: {stats['updated_rows']} 行")
            logger.info(f"[统计] 总计处理图片: {stats['total_images']} 张")
            logger.info(f"[统计] 成功转存: {stats['success_count']} 张")
            logger.info(f"[统计] 失败: {stats['total_images'] - stats['success_count']} 张")

        except Exception as e:
            logger.error(f"[列] ❌ 处理列时出错: {str(e)}")

    def process_row(self, table_name: str, column_name: str, row: Dict[str, Any], stats: Dict[str, int]) -> None:
        """处理单行数据"""
        row_id = row['_id']
        images = row.get(column_name, [])
        if not images:
            return

        if isinstance(images, str):
            images = [images]

        logger.info(f"\n[行] 📝 处理行 {row_id}")
        logger.info(f"[行] 发现 {len(images)} 张图片")

        new_images = []
        updated = False

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
            new_url = self.process_image(image_url)

            if new_url:
                new_images.append(new_url)
                updated = True
                stats['success_count'] += 1
            else:
                new_images.append(image)

            # 避免请求过于频繁
            time.sleep(1)

        if updated:
            try:
                self.base.update_row(table_name, row_id, {column_name: new_images})
                logger.info(f"[行] ✅ 更新成功")
                stats['updated_rows'] += 1
            except Exception as e:
                logger.error(f"[行] ❌ 更新失败: {str(e)}")

def main():
    """主函数"""
    try:
        # 加载配置
        config = Config()
        
        # 获取所有base配置
        bases = config.seatable_config['bases']
        logger.info(f"[主程序] 📚 发现 {len(bases)} 个base待处理")
        
        # 处理每个base
        for base_config in bases:
            base_name = base_config.get('name', '未命名')
            base_token = base_config.get('token')
            
            logger.info(f"\n[Base] 🔄 开始处理base: {base_name}")
            
            try:
                # 初始化SeaTable管理器
                manager = SeaTableManager(config, base_token)
                
                # 获取所有表格
                metadata = manager.base.get_metadata()
                tables = metadata.get('tables', [])
                
                if not tables:
                    logger.error(f"[Base] ❌ {base_name} 未找到任何表格")
                    continue
                
                logger.info(f"[Base] 📚 {base_name} 发现 {len(tables)} 个表格")
                
                # 处理每个表格
                for table in tables:
                    manager.process_table(table['name'])
                    
                logger.info(f"[Base] ✨ {base_name} 处理完成")
                
            except Exception as e:
                logger.error(f"[Base] ❌ {base_name} 处理出错: {str(e)}")
                continue
            
        logger.info("[主程序] ✨ 所有base处理完成")
        
    except Exception as e:
        logger.error(f"[主程序] ❌ 程序执行出错: {str(e)}")
        raise

if __name__ == '__main__':
    main() 