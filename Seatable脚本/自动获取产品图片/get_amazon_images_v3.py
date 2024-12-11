# 配置参数
SERVER_URL = 'https://cloud.seatable.cn'
API_TOKEN = '7d67fb2e9a309d5f5c25099d65c844a01d7c6c40'
TABLE_NAME = 'Task'

from seatable_api import Base
import requests
import re
import time
import json
from datetime import datetime
import sys
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import random
import hashlib

# 配置重试策略
retry_strategy = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
    connect=5,
    read=5,
    redirect=3
)

# 创建带重试的session
session = requests.Session()
adapter = HTTPAdapter(
    max_retries=retry_strategy,
    pool_connections=10,
    pool_maxsize=10,
    pool_block=False
)
session.mount("http://", adapter)
session.mount("https://", adapter)

def get_all_rows(base, table_name):
    """
    分页获取表格中的所有数据
    """
    print_log("开始获取表格数据...", "INFO")
    all_rows = []
    page_size = 1000
    start = 0
    
    while True:
        rows = base.list_rows(table_name, start=start, limit=page_size)
        if not rows:
            break
        all_rows.extend(rows)
        start += page_size
        print_log(f"已获取 {len(all_rows)} 条数据", "INFO")
    
    print_log(f"总共获取 {len(all_rows)} 条数据", "SUCCESS")
    return all_rows

class RunningHistory:
    def __init__(self):
        self.history = {}
        self.stats = {
            'reused': 0,    # 重复使用的次数
            'new': 0,       # 新提取的次数
            'unchanged': 0   # URL相同的次数
        }
    
    def get_url_hash(self, url):
        """获取URL的哈希值"""
        # 移除URL中的跟踪参数，只保留基本的产品ID部分
        clean_url = re.sub(r'/ref=.*$', '', url)
        clean_url = re.sub(r'\?.*$', '', clean_url)
        return hashlib.md5(clean_url.encode()).hexdigest()
    
    def add_record(self, url, image_url, success=True):
        """添加记录"""
        if not url:
            return
        url_hash = self.get_url_hash(url)
        if url_hash not in self.history:
            self.history[url_hash] = {
                'url': url,
                'image_url': image_url,
                'success': success,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            self.stats['new'] += 1
    
    def get_record(self, url):
        """获取记录"""
        if not url:
            return None
        url_hash = self.get_url_hash(url)
        record = self.history.get(url_hash)
        if record and record['success']:
            self.stats['reused'] += 1
            print_log(f"使用缓存的图片URL: {record['image_url']}", "INFO")
        return record
    
    def clear_history(self):
        """清理所有缓存"""
        self.history.clear()
        print_log("已清理所有缓存", "INFO")

def print_log(message, status=""):
    """
    青龙面板标准日志输出格式
    status: 可以是 [SUCCESS] [ERROR] [WARN] [INFO] 等
    """
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if status:
        print(f"{time_str} [{status}] {message}")
    else:
        print(f"{time_str} {message}")

def get_random_delay():
    """
    生成随机延迟时间（1-3秒）
    """
    return random.uniform(1, 3)

def create_seatable_connection(api_token, server_url, max_retries=3):
    """
    创建SeaTable连接，带重试机制
    """
    for attempt in range(max_retries):
        try:
            base = Base(api_token, server_url)
            base.auth()
            return base
        except Exception as e:
            if attempt < max_retries - 1:
                delay = random.uniform(1, 3)
                print_log(f"SeaTable连接失败，{delay:.1f}秒后重试: {str(e)}", "WARN")
                time.sleep(delay)
            else:
                raise e

def verify_image_size(image_url, min_size=1000):
    """
    验证图片尺寸是否达到最低要求
    Args:
        image_url: 图片URL
        min_size: 最小边长要求（像素）
    Returns:
        bool: 是否满足尺寸要求
    """
    try:
        # 使用stream模式下载图片头部信息
        response = session.get(image_url, stream=True, timeout=5)
        if response.status_code != 200:
            return False
            
        # 读取图片的前32KB来获取尺寸信息
        image_data = response.raw.read(32768)
        
        # 使用BytesIO避免下载整个图片
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(image_data))
        
        # 获取图片尺寸
        width, height = img.size
        print_log(f"图片尺寸: {width}x{height} 像素", "INFO")
        
        # 检查最小边长是否达标
        return min(width, height) >= min_size
        
    except Exception as e:
        print_log(f"验证图片尺寸时出错: {str(e)}", "WARN")
        return False
    finally:
        if 'response' in locals():
            response.close()

def verify_image_url(image_url, check_size=True):
    """
    验证图片URL是否有效且满足尺寸要求
    """
    try:
        # 基本可访问性检查
        response = session.head(image_url, timeout=5)
        if response.status_code != 200:
            return False
            
        # 检查是否需要验证尺寸
        if check_size:
            return verify_image_size(image_url)
            
        return True
    except Exception as e:
        print_log(f"验证图片URL时出错: {str(e)}", "WARN")
        return False

def update_row_with_retry(base, table_name, row_id, data, max_retries=3):
    """
    更新行数据，带重试机制
    """
    for attempt in range(max_retries):
        try:
            base.update_row(table_name, row_id, data)
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                delay = random.uniform(1, 3)
                print_log(f"更新数据失败，{delay:.1f}秒后重试: {str(e)}", "WARN")
                time.sleep(delay)
            else:
                raise e

def get_amazon_domain(url):
    """
    获取亚马逊链接的域名和站点信息
    """
    domain_map = {
        'amazon.com': 'US',
        'amazon.ca': 'CA',
        'amazon.co.uk': 'UK',
        'amazon.de': 'DE',
        'amazon.fr': 'FR',
        'amazon.it': 'IT',
        'amazon.es': 'ES',
        'amazon.co.jp': 'JP',
        'amazon.com.au': 'AU',
        'amazon.in': 'IN',
        'amazon.com.mx': 'MX',
        'amazon.com.br': 'BR',
        'amazon.nl': 'NL',
        'amazon.sg': 'SG',
        'amazon.ae': 'AE',
        'amazon.sa': 'SA',
        'amazon.se': 'SE',
        'amazon.pl': 'PL',
        'amazon.tr': 'TR'
    }
    
    for domain in domain_map:
        if domain in url:
            return domain, domain_map[domain]
    return 'amazon.com', 'US'  # 默认返回美国站点

def optimize_amazon_image_url(url):
    """
    优化亚马逊图片URL以获取高清版本
    
    Args:
        url: 原始图片URL
    Returns:
        优化后的URL
    """
    if not url:
        return url
        
    # 1. 提取图片ID和扩展名
    match = re.search(r'/images/I/([^\.]+).*\.(jpg|png)', url)
    if not match:
        return url
        
    image_id = match.group(1)
    ext = match.group(2)
    
    # 2. 构建标准格式的高清URL
    hd_url = f"https://m.media-amazon.com/images/I/{image_id}._AC_SL1500_.{ext}"
    
    # 3. 验证高清URL是否可用
    if verify_image_url(hd_url, check_size=True):
        return hd_url
        
    # 4. 如果1500不可用，尝试其他尺寸
    sizes = [1200, 1000, 800]
    for size in sizes:
        alt_url = f"https://m.media-amazon.com/images/I/{image_id}._AC_SL{size}_.{ext}"
        if verify_image_url(alt_url, check_size=True):
            return alt_url
            
    # 5. 如果所有高清版本都不可用，返回原始URL
    print_log("无法获取高清版本，使用原始URL", "WARN")
    return url

def get_amazon_image(url, history, max_retries=5):
    """
    从亚马逊产品页面获取主图片URL，带重试机制
    """
    print_log(f"开始处理链接: {url}", "INFO")
    
    # 检查运行中的历史记录
    history_record = history.get_record(url)
    if history_record:
        if history_record['success']:
            print_log(f"从历史记录中获取图片: {history_record['image_url']}", "SUCCESS")
            return history_record['image_url']
        else:
            print_log("该链接之前获取失败，将重新尝试", "WARN")
    
    # 处理URL格式
    if not url.startswith('http'):
        url = 'https://' + url
    
    # 移除URL中的跟踪参数，只保留基本的产品ID
    url = re.sub(r'/ref=.*$', '', url)  # 移除ref参数
    url = re.sub(r'\?.*$', '', url)     # 移除所有查询参数
    
    # 获取站点信息
    domain, site = get_amazon_domain(url)
    print_log(f"识别到站点: {site} ({domain})", "INFO")
    
    # 更新请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }
    
    # 图片URL优先级列表
    image_patterns = [
        # 高清图片URL (优先使用data-a-dynamic-image中的最大尺寸)
        r'data-a-dynamic-image="([^"]+)"',
        # 原始高清图片
        r'data-old-hires="(https://[^"]+)"',
        r'data-zoom-hires="(https://[^"]+)"',
        # 主图片URL
        r'id="landingImage"[^>]+src="(https://[^"]+)"',
        r'id="imgBlkFront"[^>]+src="(https://[^"]+)"',
        # 其他图片URL
        r'"large":"(https://[^"]+\.jpg)"',
        r'"main":"(https://[^"]+\.jpg)"'
    ]
    
    for attempt in range(max_retries):
        try:
            if attempt == 0:
                initial_delay = random.uniform(2, 4)
                print_log(f"初始等待 {initial_delay:.1f} 秒...", "INFO")
                time.sleep(initial_delay)
            elif attempt > 0:
                delay = random.uniform(3, 6)
                print_log(f"第 {attempt + 1} 次重试获取图片... (等待 {delay:.1f} 秒)", "WARN")
                time.sleep(delay)
            
            # 配置请求选项
            request_options = {
                'headers': headers,
                'timeout': (10, 20),  # (连接超时, 读取超时)
                'allow_redirects': True,
                'verify': True,
                'stream': True
            }
            
            # 获取页面内容
            with session.get(url, **request_options) as response:
                if response.status_code == 301 or response.status_code == 302:
                    url = response.headers['Location']
                    print_log(f"跟随重定向到: {url}", "INFO")
                    continue
                    
                if response.status_code != 200:
                    print_log(f"页面请求失败: HTTP {response.status_code}", "ERROR")
                    continue
                
                # 使用流式读取内容
                content = ''
                for chunk in response.iter_content(chunk_size=8192, decode_unicode=True):
                    if chunk:
                        content += chunk
                
                # 1. 首先尝试从data-a-dynamic-image中获取（���常包含最高质量的图片）
                dynamic_image_match = re.search(r'data-a-dynamic-image="([^"]+)"', content)
                if dynamic_image_match:
                    try:
                        image_dict = json.loads(dynamic_image_match.group(1).replace('&quot;', '"'))
                        # 获取最大尺寸的图片URL
                        largest_image = max(image_dict.items(), key=lambda x: int(x[1][0]) * int(x[1][1]))
                        image_url = largest_image[0]
                        print_log(f"成功获取动态图片: {image_url}", "SUCCESS")
                        history.add_record(url, image_url, True)
                        return image_url
                    except Exception as e:
                        print_log(f"解析动态图片数据失败: {str(e)}", "WARN")
                
                # 2. 尝试其他图片URL模式
                for pattern in image_patterns:
                    matches = re.findall(pattern, content)
                    if matches:
                        for match in matches:
                            if isinstance(match, tuple):
                                match = match[0]
                            image_url = match.replace('\\', '')
                            
                            # 确保获取高清图片
                            if '_SL1500_' not in image_url and '._AC_' in image_url:
                                image_url = image_url.replace('._AC_', '._AC_SL1500_')
                            elif '_SX' in image_url:
                                image_url = re.sub(r'\._SX\d+_', '._SX1500_', image_url)
                            elif '_SY' in image_url:
                                image_url = re.sub(r'\._SY\d+_', '._SY1500_', image_url)
                            elif '_SR' in image_url:
                                image_url = re.sub(r'\._SR\d+,\d+_', '._SR1500,1500_', image_url)
                            
                            # 验证图片URL是否有效
                            if 'sprite' not in image_url.lower() and 'placeholder' not in image_url.lower():
                                if verify_image_url(image_url):
                                    print_log(f"成功获取图片: {image_url}", "SUCCESS")
                                    history.add_record(url, image_url, True)
                                    return image_url
                                else:
                                    print_log(f"图片URL无效: {image_url}", "WARN")
                
                print_log(f"第 {attempt + 1} 次尝试未找到图片", "WARN")
                
        except requests.Timeout:
            print_log(f"第 {attempt + 1} 次请求超时", "ERROR")
        except requests.TooManyRedirects:
            print_log(f"第 {attempt + 1} 次请求重定向次数过多", "ERROR")
            # 如果重定向次数过多，尝试清除URL中的参数
            url = re.sub(r'\?.*$', '', url)
        except Exception as e:
            print_log(f"第 {attempt + 1} 次请求出错: {str(e)}", "ERROR")
    
    print_log(f"经过 {max_retries} 次尝试后仍未找到图片", "ERROR")
    history.add_record(url, None, False)
    return None

def process_single_row(row, base, table_name, total, index, history):
    """
    处理单行数据
    """
    try:
        print_log(f"开始处理第 {index}/{total} 行数据:", "INFO")
        product_url = row.get('产品链接')
        
        if not product_url:
            print_log("产品链接为空，跳过处理", "WARN")
            return {'status': 'skipped', 'reason': 'empty_link'}
        
        # 获取当前图片URL
        current_image = row.get('产品图片')
        current_image_url = current_image[0] if current_image and isinstance(current_image, list) and len(current_image) > 0 else None
        
        # 获取新的图片URL并优化
        new_image_url = get_amazon_image(product_url, history)
        if not new_image_url:
            print_log("获取新图片失败", "ERROR")
            return {'status': 'failed', 'reason': 'no_image'}
            
        # 只对新获取的图片URL进行优化
        optimized_new = optimize_amazon_image_url(new_image_url)
        print_log(f"优化后的新图片URL: {optimized_new}", "INFO")
        
        # 直接比较当前URL和优化后的新URL
        if current_image_url:
            # 清理URL中的跟踪参数进行比较
            clean_current = re.sub(r'\?.*$', '', current_image_url)
            clean_new = re.sub(r'\?.*$', '', optimized_new)
            
            if clean_current == clean_new:
                print_log("图片URL相同，无需更新", "INFO")
                history.stats['unchanged'] += 1
                return {'status': 'skipped', 'reason': 'unchanged'}
        
        # 更新图片URL
        row_id = row['_id']
        if update_row_with_retry(base, table_name, row_id, {'产品图片': [optimized_new]}):
            print_log("图片更新成功", "SUCCESS")
            return {'status': 'updated'}
        
        return {'status': 'failed', 'reason': 'update_failed'}
        
    except Exception as e:
        print_log(f"处理数据时出错: {str(e)}", "ERROR")
        return {'status': 'failed', 'reason': 'process_error'}

def format_amazon_image_url(image_id, size=1500):
    """
    格式化Amazon图片URL
    
    Args:
        image_id: 图片ID (如 '712mKQsLEbL')
        size: 图片尺寸 (默认1500)
        
    Returns:
        格式化后的URL
    """
    return f"https://m.media-amazon.com/images/I/{image_id}._AC_SL{size}_.jpg"

def clean_image_url(url):
    """清理和标准化图片URL"""
    if not url:
        return url
        
    # 移除._A部分，这是一个错误的URL格式
    url = url.replace('._A.', '.')
    
    # 确保使用最高质量的图片
    if '_AC_' in url:
        # 提取基本URL部分
        base_url = url.split('_AC_')[0]
        # 添加最高质量后缀
        url = f"{base_url}_AC_SL1500_.jpg"
        
    return url

def extract_image_url(url, session, history):
    """从产品页面提取图片URL"""
    try:
        # 获取页面内容
        response = session.get(url, timeout=10)
        
        if response.status_code != 200:
            print_log(f"页面请求失败: HTTP {response.status_code}", "ERROR")
            return None
            
        # 尝试提取图片URL
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. 首先尝试从动态加载的数据中提取
        scripts = soup.find_all('script', type='text/javascript')
        for script in scripts:
            if 'colorImages' in script.text:
                try:
                    # 提取JSON数据
                    json_str = re.search(r'colorImages\s*:\s*({.*?}),\s*\n', script.text)
                    if json_str:
                        data = json.loads(json_str.group(1))
                        if data and 'initial' in data:
                            image_url = data['initial'][0]['hiRes']
                            # 清理和标准化URL
                            image_url = clean_image_url(image_url)
                            return image_url
                except Exception as e:
                    print_log(f"解析动态图片数据失败: {str(e)}", "WARN")
    except Exception as e:
        print_log(f"从产品页面提取图片URL时出错: {str(e)}", "ERROR")
        return None

def main():
    """
    主函数
    """
    try:
        print_log("正在初始化程序...", "INFO")
        start_time = datetime.now()
        print_log("="*50)
        print_log("开始执行自动获取亚马逊产品图片任务", "INFO")
        print_log("="*50)
        
        print_log("检查网络连接...", "INFO")
        try:
            requests.get(SERVER_URL, timeout=5)
            print_log("网络连接正常", "SUCCESS")
        except Exception as e:
            print_log(f"网络连接测试失败: {str(e)}", "ERROR")
            raise
        
        print_log("正在连接到SeaTable...", "INFO")
        base = create_seatable_connection(API_TOKEN, SERVER_URL)
        print_log("SeaTable连接成功", "SUCCESS")
        
        # 获取表格数据
        rows = get_all_rows(base, TABLE_NAME)
        total_rows = len(rows)
        
        # 初始化结果统计
        results = {
            'updated': 0,
            'skipped': 0,
            'failed': 0,
            'empty_links': 0,
            'unchanged': 0,
            'kept_original': 0,
            'from_history': 0
        }
        
        # 创建运行时历史记录对象
        history = RunningHistory()
        
        # 顺序处理每一行数据
        for index, row in enumerate(rows, 1):
            print_log("-"*30)
            
            # 处理单行数据
            result = process_single_row(row, base, TABLE_NAME, total_rows, index, history)
            
            # 更新统计
            if result['status'] == 'updated':
                results['updated'] += 1
            elif result['status'] == 'skipped':
                results['skipped'] += 1
                if result['reason'] == 'empty_link':
                    results['empty_links'] += 1
                elif result['reason'] == 'unchanged':
                    results['unchanged'] += 1
                elif result['reason'] == 'kept_original':
                    results['kept_original'] += 1
            elif result['status'] == 'failed':
                results['failed'] += 1
            
            # 显示进度
            progress = index / total_rows * 100
            print_log(f"当前进度: {progress:.1f}% ({index}/{total_rows})", "INFO")
            
            # 处理间隔
            if index < total_rows:
                delay = random.uniform(2, 4)
                print_log(f"等待 {delay:.1f} 秒后继续...", "INFO")
                time.sleep(delay)
        
        # 计算总耗时
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # 输出最终统计
        print_log("\n" + "="*50)
        print_log("任务执行完成，最终统计：", "INFO")
        print_log("="*50)
        print_log(f"总处理数: {total_rows} 条数据", "INFO")
        print_log(f"执行耗时: {duration:.1f} 秒", "INFO")
        print_log("-"*50)
        print_log("处理结果详情:", "INFO")
        print_log(f"✅ 更新成功: {results['updated']} 条", "SUCCESS")
        print_log(f"⏭️ 无需更新: {results['unchanged']} 条 (图片未变化)", "INFO")
        print_log(f"⚠️ 空链接数: {results['empty_links']} 条", "WARN")
        print_log(f"📝 保留原图: {results['kept_original']} 条", "INFO")
        print_log(f"❌ 完全失败: {results['failed']} 条 (无法获取新图片且无原图)", "ERROR")
        print_log(f"♻️ 重复链接: {history.stats['reused']} 条", "INFO")
        print_log("-"*50)
        print_log("汇总统计:", "INFO")
        print_log(f"✅ 成功处理: {results['updated']} 条", "SUCCESS")
        print_log(f"⏭️ 跳过处理: {results['skipped']} 条", "INFO")
        print_log(f"❌ 处理失败: {results['failed']} 条", "ERROR")
        print_log("="*50)
        
        # 在最终统计中添加新的统计项
        print_log(f"🔄 URL相同跳过: {history.stats['unchanged']} 条", "INFO")
        print_log(f"♻️ 重复链接复: {history.stats['reused']} 条", "INFO")
        print_log(f"🆕 新获取图片数: {history.stats['new']} 条", "INFO")
        
        # 在最终统计之后，程序结束前清理缓存
        print_log("\n正在清理缓存...", "INFO")
        history.clear_history()
        
    except Exception as e:
        print_log(f"程序执行出错: {str(e)}", "ERROR")
        
if __name__ == '__main__':
    try:
        print_log("开始执行主程序", "INFO")
        main()
    except Exception as e:
        print_log(f"程序执行出现致命错误: {str(e)}", "ERROR")
        import traceback
        print_log(f"错误详情:\n{traceback.format_exc()}", "ERROR") 