import os
import json
import time
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class ProgressManager:
    """进度管理器"""
    def __init__(self, progress_file: str, save_interval: int = 300):
        self.progress_file = progress_file
        self.save_interval = save_interval
        self.last_save_time = 0
        self.progress: Dict[str, Any] = self.load_progress()

    def load_progress(self) -> Dict[str, Any]:
        """加载进度"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[进度] ❌ 加载进度文件失败: {str(e)}")
        return {}

    def save_progress(self, force: bool = False) -> None:
        """保存进度"""
        current_time = time.time()
        if not force and current_time - self.last_save_time < self.save_interval:
            return

        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(self.progress, f, ensure_ascii=False, indent=2)
            self.last_save_time = current_time
            logger.debug("[进度] ✅ 进度保存成功")
        except Exception as e:
            logger.error(f"[进度] ❌ 保存进度失败: {str(e)}")

    def get_table_progress(self, table_name: str) -> Dict[str, Any]:
        """获取表格进度"""
        return self.progress.get(table_name, {})

    def update_table_progress(self, table_name: str, data: Dict[str, Any]) -> None:
        """更新表格进度"""
        if table_name not in self.progress:
            self.progress[table_name] = {}
        self.progress[table_name].update(data)
        self.save_progress()

    def clear_progress(self) -> None:
        """清除进度"""
        self.progress = {}
        self.save_progress(force=True)

class ImageProcessor:
    """图片处理器"""
    @staticmethod
    def get_file_extension(url: str) -> str:
        """获取文件扩展名"""
        ext = os.path.splitext(urlparse(url).path)[1]
        return ext.lower() if ext else '.jpg'

    @staticmethod
    def is_valid_image_url(url: str) -> bool:
        """检查是否是有效的图片URL"""
        if not url:
            return False
        ext = ImageProcessor.get_file_extension(url)
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        return ext in valid_extensions

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f}GB" 