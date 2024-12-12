import os
import json
import time
import logging
import tempfile
import requests
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse
from seatable_api import Base
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 定义常量
TEMP_DIR = '/ql/scripts/.temp'
LOG_DIR = '/ql/log/seatable_image_sync'
STATS_FILE = '/ql/scripts/.stats/seatable_image_sync_stats.json'

# 创建必要的目录
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)

# 配置日志
log_file = os.path.join(LOG_DIR, f'sync_{time.strftime("%Y%m%d_%H%M%S")}.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

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

    def _get_metadata(self) -> Dict:
        """获取并缓存base元数据"""
        try:
            return self.base.get_metadata()
        except Exception as e:
            logger.error(f"获取base元数据失败: {str(e)}")
            return {}

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
                logger.info(f"[表格] ℹ️ 表格中没有图片列，跳过")
                return

            logger.info(f"[表格] 📷 发现图片列: {', '.join(image_columns)}")

            # 处理每个图片列
            for column_name in image_columns:
                # 跳过名称为"产品图片"的列
                if column_name == "产品图片":
                    logger.info(f"[表格] ⏩ 跳过列: {column_name}")
                    continue
                self.process_column(table_name, column_name)

        except Exception as e:
            logger.error(f"[表格] ❌ 处理表格时出错: {str(e)}")

    def process_column(self, table_name: str, column_name: str) -> None:
        """处理单个列"""
        logger.info(f"\n[列] 📑 开始处理列: {column_name}")

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
                    self.process_row(table_name, column_name, row)

                start += len(rows)
                if len(rows) < page_size:
                    break

        except Exception as e:
            logger.error(f"[列] ❌ 处理列时出错: {str(e)}")

    def process_row(self, table_name: str, column_name: str, row: Dict[str, Any]) -> None:
        """处理单行数据"""
        row_id = row['_id']
        images = row.get(column_name, [])
        if not images:
            return

        if isinstance(images, str):
            images = [images]

        # 获取首列内容作为标识
        first_column = next(iter(row.keys()))
        first_column_value = row.get(first_column, '') if first_column != '_id' else ''
        row_info = f"{first_column_value[:30]}..." if len(str(first_column_value)) > 30 else str(first_column_value)

        logger.info("─" * 50)
        logger.info(f"[行] 📝 处理行 {row_id} [{row_info}]")
        logger.info(f"[行] 📎 当前处理列: {column_name}")
        logger.info(f"[行] 🔍 发现 {len(images)} 张图片")

        new_images = []
        updated = False
        
        # 使用实例的base_name而不是从配置中获取
        if column_name not in stats['details'][self.base_name]['tables'][table_name]['columns']:
            stats['details'][self.base_name]['tables'][table_name]['columns'][column_name] = {
                'processed': 0,
                'success': 0,
                'skipped': 0,
                'failed': 0
            }
        
        column_stats = stats['details'][self.base_name]['tables'][table_name]['columns'][column_name]

        for index, image in enumerate(images, 1):
            image_url = image.get('url', '') if isinstance(image, dict) else image

            if not image_url:
                logger.warning(f"[行] ⚠️ 第 {index} 张图片URL为空，跳过")
                new_images.append(image)
                continue

            if 'img.shuang.fun' in image_url:
                logger.info(f"[行] ⏩ 第 {index} 张图片已在图床中，跳过")
                new_images.append(image)
                stats['skipped'] += 1
                column_stats['skipped'] += 1
                continue

            stats['images'] += 1
            column_stats['processed'] += 1
            new_url = self.process_image(image_url)

            if new_url:
                new_images.append(new_url)
                updated = True
                stats['success'] += 1
                column_stats['success'] += 1
            else:
                new_images.append(image)
                stats['failed'] += 1
                column_stats['failed'] += 1

            # 避免请求过于频繁
            time.sleep(1)

        if updated:
            try:
                self.base.update_row(table_name, row_id, {column_name: new_images})
                logger.info(f"[行] ✅ 更新成功 - {column_name}")
            except Exception as e:
                logger.error(f"[行] ❌ 更新失败 - {column_name}: {str(e)}")
        
        logger.info("─" * 50)

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
        'details': {}
    }

    # 用于跟踪未命名base的计数
    unnamed_count = 0
    base_names = set()  # 用于跟踪已使用的base名称

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
        
        # 处理每个base
        for base_config in bases:
            base_token = base_config.get('token')
            config_base_name = base_config.get('name')  # 从配置中获取base名称
            
            try:
                # 初始化SeaTable管理器
                manager = SeaTableManager(config, base_token)
                
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
                
                logger.info(f"[Base] 📚 {base_name} 发现 {len(tables)} 个表格")
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
        
        # 生成详细的统计报告
        duration = time.time() - start_time
        
        # 生成报告内容
        report_lines = [
            "\n" + "=" * 50,
            "执行完成报告",
            "=" * 50,
            f"总计处理Base数: {stats['bases']}",
            f"总计处理表格数: {stats['tables']}",
            f"总计处理图片数: {stats['images']}",
            f"总计成功转存: {stats['success']}",
            f"总计跳过图片: {stats['skipped']}",
            f"总计失败图片: {stats['failed']}",
            f"执行时间: {duration:.2f}秒",
            "\n详细统计："
        ]
        
        # 添加详细统计
        for base_name, base_stats in stats['details'].items():
            report_lines.append(f"\nBase: {base_name}")
            for table_name, table_stats in base_stats['tables'].items():
                if table_stats['columns']:  # 只显示有更新的表格
                    report_lines.append(f"  表格: {table_name}")
                    for col_name, col_stats in table_stats['columns'].items():
                        if col_stats.get('processed', 0) > 0 or col_stats.get('skipped', 0) > 0:
                            report_lines.extend([
                                f"    列: {col_name}",
                                f"      - 处理图片: {col_stats.get('processed', 0)} 张",
                                f"      - 成功转存: {col_stats.get('success', 0)} 张",
                                f"      - 跳过图片: {col_stats.get('skipped', 0)} 张",
                                f"      - 失败图片: {col_stats.get('failed', 0)} 张"
                            ])
        
        # 添加结束分隔线
        report_lines.append("=" * 50)
        
        # 生成最终报告
        final_report = "\n".join(report_lines)
        
        # 输出到日志
        logger.info(final_report)
        
        # 发送通知
        notify_status('SeaTable图片同步', final_report)
        
        logger.info("[主程序] ✨ 所有base处理完成")
        
    except Exception as e:
        logger.error(f"[主程序] ❌ 程序执行出错: {str(e)}")
        notify_status('SeaTable图片同步异常', str(e))
        raise
    finally:
        # 清理临时文件
        cleanup_temp_files()

if __name__ == '__main__':
    main() 