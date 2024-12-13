import os
import json
import time
import queue
import logging
import tempfile
import threading
import requests
from typing import Dict, List, Optional, Any, Callable
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from seatable_api import Base

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 常量定义
TEMP_DIR = '/ql/scripts/.temp'
STATS_FILE = '/ql/scripts/.stats/seatable_image_sync_stats.json'
IMAGE_BED_URL = 'https://img.shuang.fun/api/tgchannel'
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
REQUEST_DELAY = 1  # 请求延迟（秒）
MAX_WORKERS = 3  # 最大工作线程数
MAX_QUEUE_SIZE = 1000  # 最大队列大小

# 需要处理的域名列表
PROCESS_DOMAINS = [
    'cloud.seatable.cn',
    'cloud.seatable.io'
]

# 创建必要的目录
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)

# 全局统计数据
stats = {
    'bases': 0,
    'tables': 0,
    'images': 0,
    'success': 0,
    'skipped': 0,
    'failed': 0,
    'ignored_domain': 0,
    'from_history': 0,
    'details': {}
}

@dataclass
class ImageTask:
    """图片处理任务"""
    url: str
    table_name: str
    column_name: str
    row_id: str
    base_name: str
    row_data: str = ''
    callback: Optional[Callable] = None

class TaskQueue:
    """任务队列管理"""
    def __init__(self, max_size: int = MAX_QUEUE_SIZE):
        self.queue = queue.Queue(maxsize=max_size)
        self._active = True
        self._lock = threading.Lock()

    def put(self, task: ImageTask):
        """添加任务到队列"""
        if self._active:
            self.queue.put(task)

    def get(self) -> Optional[ImageTask]:
        """从队列获取任务"""
        try:
            return self.queue.get(timeout=1)
        except queue.Empty:
            return None

    def stop(self):
        """停止任务队列"""
        with self._lock:
            self._active = False

    @property
    def is_active(self) -> bool:
        """队列是否活跃"""
        with self._lock:
            return self._active

class ImageProcessor:
    """图片处理工具"""
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
    def should_process_domain(url: str) -> bool:
        """检查是否需要处理该域名的图片"""
        if not url:
            return False
        try:
            domain = urlparse(url).netloc
            return any(process_domain in domain for process_domain in PROCESS_DOMAINS)
        except:
            return False

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f}GB"

    @staticmethod
    def get_temp_file(suffix: str = '.jpg') -> str:
        """获取临时文件路径"""
        temp_file = tempfile.NamedTemporaryFile(
            dir=TEMP_DIR,
            suffix=suffix,
            delete=False
        )
        temp_file.close()
        return temp_file.name

    @staticmethod
    def process_batch(tasks: List[ImageTask], manager: 'SeaTableManager') -> Dict[str, Any]:
        """批量处理图片任务"""
        results = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_task = {
                executor.submit(manager.process_single_image, task): task
                for task in tasks
            }
            
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result()
                    results[task.url] = result
                except Exception as e:
                    logger.error(f"处理图片失败 {task.url}: {str(e)}")
                    results[task.url] = None
                
                # 添加请求延迟
                time.sleep(REQUEST_DELAY)
        
        return results

class ImageHistory:
    """图片处理历史记录管理"""
    def __init__(self):
        self.current_records = {}
        self._save_lock = threading.Lock()
        self.failed_records = []  # 新增：专门存储失败记录

    def add_failed_record(self, image_url: str, error_msg: str, base_name: str = '', table_name: str = '', 
                         row_id: str = '', row_data: str = '', column_name: str = ''):
        """添加失败记录，包含完整信息"""
        with self._save_lock:
            failed_record = {
                'url': image_url,
                'error': error_msg,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'base_name': base_name,
                'table_name': table_name,
                'row_id': row_id,
                'row_data': row_data,
                'column_name': column_name
            }
            self.failed_records.append(failed_record)
            # 同时更新 current_records
            self.current_records[image_url] = {
                'status': 'failed',
                'error': error_msg,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'base_name': base_name,
                'table_name': table_name,
                'row_id': row_id,
                'row_data': row_data,
                'column_name': column_name
            }
            logger.info(f"[历史] 📝 添加失败记录: {image_url}")

    def add_success_record(self, image_url: str, image_bed_url: str):
        """添加成功记录"""
        with self._save_lock:
            # 如果之前是失败记录，从失败列表中移除
            self.failed_records = [r for r in self.failed_records if r['url'] != image_url]
            self.current_records[image_url] = {
                'status': 'success',
                'image_bed_url': image_bed_url,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }

    def get_record(self, image_url: str) -> Optional[str]:
        """获取历史记录"""
        record = self.current_records.get(image_url)
        if record and record.get('status') == 'success':
            return record['image_bed_url']
        return None

    def get_failed_records(self) -> List[Dict[str, Any]]:
        """获取所有失败记录"""
        with self._save_lock:
            failed = self.failed_records.copy()
            logger.info(f"[历史] 📊 当前失败记录数: {len(failed)}")
            return failed

    def update_record_status(self, url: str, status: str, image_bed_url: str = None):
        """更新记录状态"""
        with self._save_lock:
            if url in self.current_records:
                old_status = self.current_records[url].get('status')
                self.current_records[url]['status'] = status
                if image_bed_url:
                    self.current_records[url]['image_bed_url'] = image_bed_url
                
                # 如果状态从失败变为成功，从失败列表中移除
                if old_status == 'failed' and status == 'success':
                    self.failed_records = [r for r in self.failed_records if r['url'] != url]
                # 如果状态从成功变为失败，添加到失败列表
                elif old_status == 'success' and status == 'failed':
                    self.add_failed_record(url, "状态更新为失败")

    def clear_all_records(self):
        """清理所有记录"""
        with self._save_lock:
            failed_count = len(self.failed_records)
            self.current_records.clear()
            self.failed_records.clear()
            logger.info(f"[历史] 🧹 清理所有记录完成 (清理了 {failed_count} 条失败记录)")

class ImageBed:
    """图床管理器"""
    def __init__(self, upload_api: str, size_limit: int = 5):
        self.upload_api = upload_api
        self.size_limit = size_limit * 1024 * 1024  # 转换为字节
        self.session = create_session()

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

def create_session():
    """创建带重试的会话"""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def cleanup_temp_files():
    """清理临时文件"""
    try:
        for file in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, file)
            if os.path.isfile(file_path):
                try:
                    os.unlink(file_path)
                except Exception as e:
                    logger.error(f"清理临时文件失败: {str(e)}")
    except Exception as e:
        logger.error(f"清理临时目录失败: {str(e)}")

def notify_status(title: str, content: str):
    """发送通知到青龙面板"""
    try:
        url = 'http://localhost:5700/api/sendNotify'
        data = {
            'title': title,
            'content': content
        }
        requests.post(url, json=data, timeout=5)
    except:
        pass  # 通知失败不影响主流程

def update_stats(new_stats: Dict[str, int]):
    """更新运行统计"""
    try:
        stats = {}
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r') as f:
                stats = json.load(f)
                
        stats['last_run'] = time.strftime('%Y-%m-%d %H:%M:%S')
        stats['total_runs'] = stats.get('total_runs', 0) + 1
        stats['total_images'] = stats.get('total_images', 0) + new_stats['images']
        stats['total_success'] = stats.get('total_success', 0) + new_stats['success']
        stats['total_ignored_domain'] = stats.get('total_ignored_domain', 0) + new_stats['ignored_domain']
        
        with open(STATS_FILE, 'w') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
    except:
        pass

def check_environment() -> bool:
    """检查运行环境"""
    # 检查必要的包
    required_packages = ['seatable_api', 'requests']
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            logger.error(f"缺少必要的包: {package}")
            return False
            
    # 检查API Token配置
    if not os.getenv('SEATABLE_API_TOKENS') and not os.getenv('SEATABLE_API_TOKEN'):
        logger.error("未配置API Token")
        return False
        
    return True

class Config:
    """配置管理"""
    def __init__(self):
        """初始化配置"""
        self.config = self._load_from_env()

    def _parse_base_tokens(self, tokens_str: str) -> List[Dict[str, str]]:
        """解析base tokens
        格式1: base_name1:token1,base_name2:token2
        格式2: token1,token2
        """
        if not tokens_str:
            return []
            
        bases = []
        tokens = [t.strip() for t in tokens_str.split(',') if t.strip()]
        
        for token_info in tokens:
            if ':' in token_info:
                # name:token 格式
                name, token = token_info.split(':', 1)
                bases.append({'name': name.strip(), 'token': token.strip()})
            else:
                # 纯token格式
                bases.append({'token': token_info})
        
        return bases

    def _load_from_env(self) -> Dict[str, Any]:
        """从环境变量加载配置"""
        # 获取并解析base tokens
        base_tokens_str = os.getenv('SEATABLE_API_TOKENS') or os.getenv('SEATABLE_API_TOKEN')
        if not base_tokens_str:
            raise Exception("环境变量未设置: SEATABLE_API_TOKENS 或 SEATABLE_API_TOKEN")
            
        bases = self._parse_base_tokens(base_tokens_str)
        if not bases:
            raise Exception("无效的API Token配置")

        return {
            'seatable': {
                'bases': bases,
                'server_url': os.getenv('SEATABLE_SERVER_URL', 'https://cloud.seatable.cn')
            },
            'image_bed': {
                'upload_api': os.getenv('IMAGE_BED_API', 'https://img.shuang.fun/api/tgchannel'),
                'size_limit': int(os.getenv('IMAGE_SIZE_LIMIT', '5'))  # 默认5MB
            }
        }

class SeaTableManager:
    """SeaTable管理器"""
    def __init__(self, config: Config, api_token: str):
        self.config = config
        self.api_token = api_token
        self.base = self._init_base()
        self._base_name = None
        image_bed_config = config.config['image_bed']
        self.image_bed = ImageBed(
            upload_api=image_bed_config['upload_api'],
            size_limit=image_bed_config['size_limit']
        )
        self.session = create_session()
        self.image_history = ImageHistory()
        self.task_queue = TaskQueue()
        self.processing = False
        self._stats_lock = threading.Lock()
        # 添加日志记录字典
        self.processing_logs = {
            'bases': {},
            'success_records': [],
            'failure_records': [],
            'skip_count': 0,
            'ignored_domain_count': 0
        }

    @property
    def base_name(self) -> str:
        """获取base名称的属性"""
        return self._base_name if self._base_name else '未命名'

    @base_name.setter
    def base_name(self, value: str):
        """设置base名称的属性"""
        self._base_name = value

    def _init_base(self) -> Base:
        """初始化SeaTable连接"""
        seatable_config = self.config.config['seatable']
        base = Base(self.api_token, seatable_config['server_url'])
        base.auth()
        return base

    def _download_image(self, image_url: str) -> Optional[str]:
        """下载图片"""
        try:
            # 创建临时文件
            ext = ImageProcessor.get_file_extension(image_url)
            temp_file = ImageProcessor.get_temp_file(ext)

            logger.info(f"[下载] 📥 开始下载: {image_url}")

            try:
                self.base.download_file(image_url, temp_file)
                file_size = os.path.getsize(temp_file)
                if file_size > 0:
                    logger.info(f"[下载] ✅ 下载成功: {ImageProcessor.format_file_size(file_size)}")
                    return temp_file
                else:
                    logger.error("[下载] ❌ 下载失败: 文件大小为0")
            except Exception as e:
                logger.error(f"[下载] ❌ 下载失败: {str(e)}")

            if os.path.exists(temp_file):
                os.unlink(temp_file)
            return None

        except Exception as e:
            logger.error(f"[下载] ❌ 下载过程出错: {str(e)}")
            return None

    def process_image(self, url: str) -> Optional[str]:
        """处理单个图片"""
        try:
            # 1. 下载图片
            temp_file = self._download_image(url)
            if not temp_file:
                return None

            try:
                # 2. 上传到图床
                new_url = self.image_bed.upload_image(temp_file)
                if new_url:
                    logger.info(f"[处理] ✅ 成功: {new_url}")
                return new_url

            finally:
                # 清理临时文件
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

        except Exception as e:
            logger.error(f"[处理] ❌ 处理失败: {str(e)}")
            return None

    def process_single_image(self, task: ImageTask) -> Optional[str]:
        """处理单个图片任务"""
        try:
            # 1. 首先检查域名
            if not ImageProcessor.should_process_domain(task.url):
                with self._stats_lock:
                    stats['ignored_domain'] += 1
                    self._log_ignored_domain(task)
                return None

            # 2. 检查是否为空URL
            if not task.url:
                with self._stats_lock:
                    stats['skipped'] += 1
                    self._log_skip(task)
                return None

            # 3. 检查是否已在图床中
            if 'img.shuang.fun' in task.url:
                with self._stats_lock:
                    stats['skipped'] += 1
                    self._log_skip(task)
                return task.url

            # 4. 检查历史记录
            if history_url := self.image_history.get_record(task.url):
                with self._stats_lock:
                    stats['from_history'] += 1
                    self._log_success(task, history_url)
                return history_url

            # 5. 处理新图片
            logger.info(f"[处理] 📥 开始处理: {task.url}")
            with self._stats_lock:
                stats['images'] += 1

            # 6. 下载并上传图片
            try:
                new_url = self.process_image(task.url)
                
                # 7. 更新统计和历史记录
                with self._stats_lock:
                    if new_url:
                        stats['success'] += 1
                        self.image_history.add_success_record(task.url, new_url)
                        self._log_success(task, new_url)
                        logger.info(f"[处理] ✅ 成功: {new_url}")
                    else:
                        stats['failed'] += 1
                        error_msg = "下载或上传失败"
                        self.image_history.add_failed_record(
                            task.url,
                            error_msg,
                            base_name=task.base_name,
                            table_name=task.table_name,
                            row_id=task.row_id,
                            row_data=task.row_data,
                            column_name=task.column_name
                        )
                        self._log_failure(task, error_msg)
                        logger.error(f"[处理] ❌ 失败: {error_msg}")

                return new_url

            except Exception as e:
                error_msg = str(e)
                with self._stats_lock:
                    stats['failed'] += 1
                    self.image_history.add_failed_record(
                        task.url,
                        error_msg,
                        base_name=task.base_name,
                        table_name=task.table_name,
                        row_id=task.row_id,
                        row_data=task.row_data,
                        column_name=task.column_name
                    )
                    self._log_failure(task, error_msg)
                logger.error(f"[处理] ❌ 处理出错: {error_msg}")
                return None

        except Exception as e:
            error_msg = str(e)
            with self._stats_lock:
                stats['failed'] += 1
                self.image_history.add_failed_record(
                    task.url,
                    error_msg,
                    base_name=task.base_name,
                    table_name=task.table_name,
                    row_id=task.row_id,
                    row_data=task.row_data,
                    column_name=task.column_name
                )
                self._log_failure(task, error_msg)
            logger.error(f"[处理] ❌ 处理出错: {error_msg}")
            return None

    def update_row_callback(self, task: ImageTask, new_url: str):
        """更新行数据的回调函数"""
        try:
            self.base.update_row(task.table_name, task.row_id, {
                task.column_name: new_url
            })
            logger.info(f"[更新] ✅ {task.table_name} - {task.row_id} - {task.column_name}")
        except Exception as e:
            logger.error(f"[更新] ❌ 更新失败: {str(e)}")

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
                logger.info(f"[表格] ℹ️ 表格中没有图片列，跳过")
                return

            logger.info(f"[表格] 📷 发现图片列: {', '.join(image_columns)}")

            # 使用线程池处理列
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = [
                    executor.submit(self.process_column, table_name, column_name)
                    for column_name in image_columns
                    if column_name != "产品图片"  # 跳过产品图片列
                ]
                
                for future in as_completed(futures):
                    try:
                        rows_count = future.result()
                        if rows_count:
                            self._update_table_total_rows(self.base_name, table_name, rows_count)
                    except Exception as e:
                        logger.error(f"[表格] ❌ 处理列时出错: {str(e)}")

        except Exception as e:
            logger.error(f"[表格] ❌ 处理表格时出错: {str(e)}")

    def process_column(self, table_name: str, column_name: str) -> Optional[int]:
        """处理单个列"""
        logger.info(f"\n[列] 📑 开始处理列: {column_name}")

        try:
            # 分页处理
            page_size = 1000
            start = 0
            total_processed = 0

            while True:
                # 获取当前页数据
                rows = self.base.list_rows(table_name, start=start, limit=page_size)
                if not rows:
                    break

                if total_processed == 0:
                    logger.info(f"[列] 📄 发现 {len(rows)} 条记录")
                total_processed += len(rows)

                # 处理每一行
                for row in rows:
                    images = row.get(column_name, [])
                    if not images:
                        continue

                    if isinstance(images, str):
                        images = [images]

                    # 获取首列内容作为标识
                    first_column = next(iter(row.keys()))
                    first_column_value = row.get(first_column, '') if first_column != '_id' else ''
                    row_info = f"{first_column_value[:30]}..." if len(str(first_column_value)) > 30 else str(first_column_value)

                    # 初始化新图片列表
                    new_images = []
                    updated = False

                    # 处理每个图片
                    for image in images:
                        image_url = image.get('url', '') if isinstance(image, dict) else image
                        
                        task = ImageTask(
                            url=image_url,
                            table_name=table_name,
                            column_name=column_name,
                            row_id=row['_id'],
                            base_name=self.base_name,
                            row_data=row_info
                        )
                        
                        # 处理单个图片
                        new_url = self.process_single_image(task)
                        
                        if new_url:
                            new_images.append(new_url)
                            updated = True
                        else:
                            new_images.append(image)

                    # 更新行数据
                    if updated:
                        try:
                            self.base.update_row(table_name, row['_id'], {column_name: new_images})
                            logger.info(f"[更新] ✅ 行更新成功: {row_info}")
                        except Exception as e:
                            logger.error(f"[更新] ❌ 行更新失败: {str(e)}")

                start += len(rows)
                if len(rows) < page_size:
                    break

                # 添加处理间隔
                time.sleep(REQUEST_DELAY)

            if total_processed > 0:
                logger.info(f"[列] ✨ 处理完成，共 {total_processed} 条记录")
                return total_processed

        except Exception as e:
            logger.error(f"[列] ❌ 处理出错: {str(e)}")
            raise  # 重新抛出异常，让上层处理

        return None

    def _process_batch_tasks(self, tasks: List[ImageTask]):
        """处理一批任务"""
        try:
            results = ImageProcessor.process_batch(tasks, self)
            logger.info(f"[批处理] ✅ 完成处理 {len(results)} 个任务")
        except Exception as e:
            logger.error(f"[批处理] ❌ 处理失败: {str(e)}")

    def retry_failed_images(self):
        """重试处理失败的图片"""
        failed_records = self.image_history.get_failed_records()
        if not failed_records:
            logger.info("[重试] ℹ️ 没有失败记录")
            return

        logger.info(f"\n[重试] 🔄 开始处理 {len(failed_records)} 个失败记录")
        
        # 初始化重试统计
        retry_stats = {
            'total': len(failed_records),
            'success': 0,
            'failed': 0
        }

        # 按Base和表格分组处理
        grouped_records = self._group_records_by_base_table(failed_records)
        
        # 处理每个分组
        for base_name, tables in grouped_records.items():
            logger.info(f"\n[重试] 📚 处理Base: {base_name}")
            for table_name, records in tables.items():
                logger.info(f"[重试] 📑 处理表格: {table_name}")
                self._retry_table_records(base_name, table_name, records, retry_stats)

        # 输出重试统计
        self._print_retry_stats(retry_stats)

    def _group_records_by_base_table(self, records: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """将失败记录按Base和表格分组"""
        grouped = {}
        for record in records:
            base_name = record['base_name']
            table_name = record['table_name']
            
            if base_name not in grouped:
                grouped[base_name] = {}
            if table_name not in grouped[base_name]:
                grouped[base_name][table_name] = []
                
            grouped[base_name][table_name].append(record)
        
        return grouped

    def _retry_table_records(self, base_name: str, table_name: str, records: List[Dict[str, Any]], retry_stats: Dict[str, int]):
        """重试处理同一表格的记录"""
        # 按行分组，避免重复更新
        rows_to_update = {}
        
        for record in records:
            task = ImageTask(
                url=record['url'],
                table_name=table_name,
                column_name=record['column_name'],
                row_id=record['row_id'],
                base_name=base_name,
                row_data=record['row_data']
            )
            
            # 处理单个图片
            new_url = self.process_image(task.url)  # 直接使用 process_image 而不是 process_single_image
            
            if new_url:
                retry_stats['success'] += 1
                # 记录需要更新的行
                row_id = record['row_id']
                if row_id not in rows_to_update:
                    rows_to_update[row_id] = {
                        'column': record['column_name'],
                        'urls': []
                    }
                rows_to_update[row_id]['urls'].append(new_url)
                # 添加成功记录
                self.image_history.add_success_record(record['url'], new_url)
            else:
                retry_stats['failed'] += 1
            
            # 添加延迟避免请求过快
            time.sleep(REQUEST_DELAY)
        
        # 批量更新行数据
        self._update_rows(table_name, rows_to_update)

    def _update_rows(self, table_name: str, rows_to_update: Dict[str, Dict[str, Any]]):
        """批量更新行数据"""
        for row_id, data in rows_to_update.items():
            try:
                self.base.update_row(
                    table_name,
                    row_id,
                    {data['column']: data['urls']}
                )
                logger.info(f"[重试] ✅ 更新成功: {row_id}")
            except Exception as e:
                logger.error(f"[重试] ❌ 更新失败 {row_id}: {str(e)}")

    def _print_retry_stats(self, stats: Dict[str, int]):
        """输出重试统计信"""
        logger.info("\n" + "=" * 50)
        logger.info("重试处理报告")
        logger.info("=" * 50)
        logger.info(f"总计重试: {stats['total']}")
        logger.info(f"成功转换: {stats['success']}")
        logger.info(f"仍然失败: {stats['failed']}")
        logger.info("=" * 50)

    def _log_success(self, task: ImageTask, new_url: str):
        """记录成功处理的图片"""
        success_record = {
            'base_name': task.base_name,
            'table_name': task.table_name,
            'row_id': task.row_id,
            'column_name': task.column_name,
            'original_url': task.url,
            'new_url': new_url,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        self.processing_logs['success_records'].append(success_record)
        
        # 更新base统计
        if task.base_name not in self.processing_logs['bases']:
            self.processing_logs['bases'][task.base_name] = {'tables': {}}
        if task.table_name not in self.processing_logs['bases'][task.base_name]['tables']:
            self.processing_logs['bases'][task.base_name]['tables'][task.table_name] = {
                'total_rows': 0,
                'success_count': 0,
                'failure_count': 0,
                'skip_count': 0,
                'ignored_domain_count': 0,
                'columns': set()
            }
        
        base_stats = self.processing_logs['bases'][task.base_name]['tables'][task.table_name]
        base_stats['success_count'] += 1
        base_stats['columns'].add(task.column_name)

    def _log_failure(self, task: ImageTask, error_msg: str):
        """记录处理失败的图片"""
        failure_record = {
            'base_name': task.base_name,
            'table_name': task.table_name,
            'row_id': task.row_id,
            'column_name': task.column_name,
            'original_url': task.url,
            'error': error_msg,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        self.processing_logs['failure_records'].append(failure_record)
        
        # 更新base统计
        if task.base_name not in self.processing_logs['bases']:
            self.processing_logs['bases'][task.base_name] = {'tables': {}}
        if task.table_name not in self.processing_logs['bases'][task.base_name]['tables']:
            self.processing_logs['bases'][task.base_name]['tables'][task.table_name] = {
                'total_rows': 0,
                'success_count': 0,
                'failure_count': 0,
                'skip_count': 0,
                'ignored_domain_count': 0,
                'columns': set()
            }
        
        base_stats = self.processing_logs['bases'][task.base_name]['tables'][task.table_name]
        base_stats['failure_count'] += 1
        base_stats['columns'].add(task.column_name)

    def _log_skip(self, task: ImageTask):
        """记录跳过的图片"""
        self.processing_logs['skip_count'] += 1
        
        # 更新base统计
        if task.base_name not in self.processing_logs['bases']:
            self.processing_logs['bases'][task.base_name] = {'tables': {}}
        if task.table_name not in self.processing_logs['bases'][task.base_name]['tables']:
            self.processing_logs['bases'][task.base_name]['tables'][task.table_name] = {
                'total_rows': 0,
                'success_count': 0,
                'failure_count': 0,
                'skip_count': 0,
                'ignored_domain_count': 0,
                'columns': set()
            }
        
        base_stats = self.processing_logs['bases'][task.base_name]['tables'][task.table_name]
        base_stats['skip_count'] += 1

    def _log_ignored_domain(self, task: ImageTask):
        """记录不处理域名的图片"""
        self.processing_logs['ignored_domain_count'] += 1
        
        # 更新base统计
        if task.base_name not in self.processing_logs['bases']:
            self.processing_logs['bases'][task.base_name] = {'tables': {}}
        if task.table_name not in self.processing_logs['bases'][task.base_name]['tables']:
            self.processing_logs['bases'][task.base_name]['tables'][task.table_name] = {
                'total_rows': 0,
                'success_count': 0,
                'failure_count': 0,
                'skip_count': 0,
                'ignored_domain_count': 0,
                'columns': set()
            }
        
        base_stats = self.processing_logs['bases'][task.base_name]['tables'][task.table_name]
        base_stats['ignored_domain_count'] += 1

    def _update_table_total_rows(self, base_name: str, table_name: str, total_rows: int):
        """更新表格总行数"""
        if base_name not in self.processing_logs['bases']:
            self.processing_logs['bases'][base_name] = {'tables': {}}
        if table_name not in self.processing_logs['bases'][base_name]['tables']:
            self.processing_logs['bases'][base_name]['tables'][table_name] = {
                'total_rows': 0,
                'success_count': 0,
                'failure_count': 0,
                'skip_count': 0,
                'ignored_domain_count': 0,
                'columns': set()
            }
        
        self.processing_logs['bases'][base_name]['tables'][table_name]['total_rows'] = total_rows

def generate_report(manager: SeaTableManager, duration: float) -> str:
    """生成处理报告"""
    lines = [
        "\n" + "=" * 50,
        f"处理报告 - {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 50,
        ""
    ]

    # 处理每个base的详细信息
    for base_name, base_info in manager.processing_logs['bases'].items():
        lines.extend([
            f"[Base: {base_name}]",
            "--------------------"
        ])

        # 处理每个表格
        for table_name, table_stats in base_info['tables'].items():
            lines.extend([
                f"表格: {table_name}",
                f"  - 总行数: {table_stats['total_rows']}",
                f"  - 处理列: {', '.join(sorted(table_stats['columns']))}"
            ])

            # 添加成功记录
            success_records = [r for r in manager.processing_logs['success_records'] 
                             if r['base_name'] == base_name and r['table_name'] == table_name]
            if success_records:
                lines.append("\n  成功记录:")
                for i, record in enumerate(success_records, 1):
                    lines.extend([
                        f"  {i}. 行ID: {record['row_id']}",
                        f"     - 列: {record['column_name']}",
                        f"     - 原图: {record['original_url']}",
                        f"     - 新图: {record['new_url']}"
                    ])

            # 添加失败记录
            failure_records = [r for r in manager.processing_logs['failure_records']
                             if r['base_name'] == base_name and r['table_name'] == table_name]
            if failure_records:
                lines.append("\n  失败记录:")
                for i, record in enumerate(failure_records, 1):
                    lines.extend([
                        f"  {i}. 行ID: {record['row_id']}",
                        f"     - 列: {record['column_name']}",
                        f"     - 原图: {record['original_url']}",
                        f"     - 错误: {record['error']}",
                        f"     - 时间: {record['timestamp']}"
                    ])

            # 添加统计信息
            lines.extend([
                "\n  统计信息:",
                f"  - 跳过图片: {table_stats['skip_count']}条",
                f"  - 不处理域名: {table_stats['ignored_domain_count']}条",
                f"  - 成功转存: {table_stats['success_count']}条",
                f"  - 失败图片: {table_stats['failure_count']}条",
                ""
            ])

    # 添加总体统计
    lines.extend([
        "=" * 50,
        "总体统计",
        "=" * 50,
        f"- 处理Base数: {len(manager.processing_logs['bases'])}",
        f"- 处理表格数: {sum(len(base_info['tables']) for base_info in manager.processing_logs['bases'].values())}",
        f"- 处理图片数: {len(manager.processing_logs['success_records']) + len(manager.processing_logs['failure_records'])}",
        f"- 成功转存: {len(manager.processing_logs['success_records'])}",
        f"- 失败图片: {len(manager.processing_logs['failure_records'])}",
        f"- 跳过图片: {manager.processing_logs['skip_count']}",
        f"- 不处理域名: {manager.processing_logs['ignored_domain_count']}",
        f"- 执行时间: {duration:.2f}秒",
        ""
    ])

    # 添加失败记录汇总
    if manager.processing_logs['failure_records']:
        lines.extend([
            "=" * 50,
            "失败记录汇总",
            "=" * 50
        ])
        
        current_base = None
        for record in manager.processing_logs['failure_records']:
            if current_base != record['base_name']:
                current_base = record['base_name']
                lines.append(f"\nBase: {current_base}")
            
            lines.extend([
                f"- {record['row_id']} ({record['table_name']})",
                f"  - 列: {record['column_name']}",
                f"  - 原图: {record['original_url']}",
                f"  - 错误: {record['error']}",
                f"  - 时间: {record['timestamp']}"
            ])

    return "\n".join(lines)

def main():
    """主函数"""
    start_time = time.time()
    global stats
    stats = {
        'bases': 0,
        'tables': 0,
        'images': 0,
        'success': 0,
        'skipped': 0,
        'failed': 0,
        'ignored_domain': 0,
        'from_history': 0,
        'details': {}
    }

    try:
        # 清理旧的临时文件
        cleanup_temp_files()
        
        # 检查环境
        if not check_environment():
            return
        
        # 加载配置
        config = Config()
        
        # 获取所有base配置
        bases = config.config['seatable']['bases']
        logger.info(f"[主程序] 📚 发现 {len(bases)} 个base待处理")
        
        # 用于跟踪未命名base的计数
        unnamed_count = 0
        base_names = set()
        
        # 创建一个全局的图片历史记录管理器
        image_history = ImageHistory()
        
        # 处理每个base
        for base_config in bases:
            base_token = base_config.get('token')
            config_base_name = base_config.get('name')
            
            try:
                # 初始化SeaTable管理器
                manager = SeaTableManager(config, base_token)
                manager.image_history = image_history  # 使用全局的历史记录管理器
                
                # 获取base元数据
                metadata = manager.base.get_metadata()
                
                # 确定base名称
                if config_base_name:
                    # 使用配置中的名称
                    base_name = config_base_name
                else:
                    # 使用API返回的名称，如果重复则添加序号
                    base_name = metadata.get('name', '未命名')
                    if base_name == '未命名' or base_name in base_names:
                        unnamed_count += 1
                        base_name = f'未命名{unnamed_count}'
                
                manager.base_name = base_name  # 更新manager中的base名称
                base_names.add(base_name)  # 记录使用过的名称
                
                logger.info(f"\n[Base] 🔄 开始处理base: {base_name}")
                
                # 获取所有表格
                tables = metadata.get('tables', [])
                
                if not tables:
                    logger.error(f"[Base] ❌ {base_name} 未找到任何表格")
                    continue
                
                logger.info(f"[Base] 发现 {base_name} 有 {len(tables)} 个表格")
                stats['bases'] += 1
                stats['details'][base_name] = {'tables': {}}
                
                # 处理每个表格
                for table in tables:
                    table_name = table['name']
                    stats['details'][base_name]['tables'][table_name] = {'columns': {}}
                    manager.process_table(table_name)
                    
                logger.info(f"[Base] ✨ {base_name} 处理完成")
                
            except Exception as e:
                logger.error(f"[Base] ❌ {base_name} 处理出错: {str(e)}")
                continue
        
        # 更新统计信息
        update_stats(stats)
        
        # 生成主处理报告
        duration = time.time() - start_time
        main_report = generate_report(manager, duration)
        logger.info(main_report)
        
        # 开始重试处理
        logger.info("\n[主程序] 🔄 开始重试处理失败记录")
        manager = SeaTableManager(config, base_token)
        manager.image_history = image_history  # 使用全局的历史记录管理器
        manager.retry_failed_images()
        
        # 生成最终报告（包含重试结果）
        final_duration = time.time() - start_time
        final_report = generate_report(manager, final_duration)
        logger.info(final_report)
        notify_status('SeaTable图片同步', final_report)
        
        # 输出失败详情
        logger.info("\n" + "=" * 50)
        logger.info("失败记录详情")
        logger.info("=" * 50)
        
        failed_details = manager.image_history.get_failed_records()
        if not failed_details:
            logger.info("没有失败记录")
        else:
            for record in failed_details:
                logger.info(f"\nBase: {record['base_name']}")
                logger.info(f"Table: {record['table_name']}")
                logger.info(f"数据: {record['row_data']}")
                logger.info(f"链接: {record['url']}")
                logger.info(f"错误: {record['error']}")
        
        logger.info("=" * 50)
        
        # 清理所有记录（放在最后）
        manager.image_history.clear_all_records()
        
        logger.info("[主程序] ✨ 所有处理完成")
        
    except Exception as e:
        logger.error(f"[主程序] ❌ 程序执行出错: {str(e)}")
        notify_status('SeaTable图片同步异常', str(e))
        raise
    finally:
        # 清理临时文件
        cleanup_temp_files()

if __name__ == '__main__':
    main()