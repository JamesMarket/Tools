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

class RunningHistory:
    def __init__(self):
        self.history = {}
        self.stats = {
            'reused': 0,  # 重复使用的次数
            'new': 0      # 新提取的次数
        }
    
    def get_url_hash(self, url):
        """获取URL的哈希值"""
        # 移除URL中的跟踪参数，只保留基本的产品ID部分
        clean_url = re.sub(r'/ref=.*$', '', url)
        clean_url = re.sub(r'\?.*$', '', clean_url)
        return hashlib.md5(clean_url.encode()).hexdigest()
    
    def add_record(self, url, image_url, success=True):
        """添加记录"""
        url_hash = self.get_url_hash(url)
        self.history[url_hash] = {
            'url': url,
            'image_url': image_url,
            'success': success,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.stats['new'] += 1
    
    def get_record(self, url):
        """获取记录"""
        url_hash = self.get_url_hash(url)
        record = self.history.get(url_hash)
        if record:
            self.stats['reused'] += 1
        return record

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
    
    # 更完整的请求头
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
                
                # 1. 首先尝试从data-a-dynamic-image中获取（通常包含最高质量的图片）
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
                    except:
                        pass
                
                # 2. 尝试其他图片URL模式
                image_patterns = [
                    # 高���图片URL
                    r'data-old-hires="(https://[^"]+)"',
                    r'data-zoom-hires="(https://[^"]+)"',
                    r'data-a-dynamic-image="([^"]+)"',
                    # 主图片URL
                    r'id="landingImage"[^>]+src="(https://[^"]+)"',
                    r'id="imgBlkFront"[^>]+src="(https://[^"]+)"',
                    r'id="main-image-container"[^>]+href="(https://[^"]+)"',
                    # 产品图片URL
                    r'"large":"(https://[^"]+\.jpg)"',
                    r'"main":"(https://[^"]+\.jpg)"',
                    r'"mainUrl":"(https://[^"]+)"',
                    # 备用图片URL
                    r'data-a-image-name="[^"]*"[^>]*src="(https://[^"]+)"',
                    r'id="main-image"[^>]+src="(https://[^"]+)"',
                    r'class="a-dynamic-image"[^>]+src="(https://[^"]+)"'
                ]
                
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
                                print_log(f"成功获取图片: {image_url}", "SUCCESS")
                                history.add_record(url, image_url, True)
                                return image_url
                
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
        
        # 获取当前的图片URL
        current_image = row.get('产品图片')
        current_image_url = None
        if current_image and isinstance(current_image, list) and len(current_image) > 0:
            current_image_url = current_image[0]
            print_log(f"当前已有图片: {current_image_url}", "INFO")
            
        # 获取新的图片URL（带重试机制）
        new_image_url = get_amazon_image(product_url, history)
        if not new_image_url:
            print_log("获取新图片失败，保持原图片不变", "WARN")
            if current_image_url:
                print_log("保留原有图片", "INFO")
                return {'status': 'skipped', 'reason': 'kept_original'}
            else:
                print_log("无原有图片", "WARN")
                return {'status': 'failed', 'reason': 'no_image'}
                
        # 比较新旧图片URL
        if current_image_url == new_image_url:
            print_log("图片未发生变化，无需更新", "INFO")
            return {'status': 'skipped', 'reason': 'unchanged'}
            
        # 更新产品图片列
        row_id = row['_id']
        print_log(f"正在更新图片...", "INFO")
        try:
            if update_row_with_retry(base, table_name, row_id, {'产品图片': [new_image_url]}):
                print_log(f"图片更新成功", "SUCCESS")
                return {'status': 'updated'}
        except Exception as e:
            print_log(f"图片更新失败: {str(e)}", "ERROR")
            if current_image_url:
                print_log("保留原有图片", "INFO")
                return {'status': 'skipped', 'reason': 'kept_original'}
            else:
                return {'status': 'failed', 'reason': 'update_failed'}
                
    except Exception as e:
        print_log(f"处理数据时出错: {str(e)}", "ERROR")
        return {'status': 'failed', 'reason': 'process_error'}

def main():
    """
    主函数
    """
    start_time = datetime.now()
    print_log("="*50)
    print_log("开始执行自动获取亚马逊产品图片任务", "INFO")
    print_log("="*50)
    
    server_url = 'https://cloud.seatable.cn'
    api_token = '7d67fb2e9a309d5f5c25099d65c844a01d7c6c40'
    
    try:
        print_log("正在连接到SeaTable...", "INFO")
        base = create_seatable_connection(api_token, server_url)
        print_log("SeaTable连接成功", "SUCCESS")
        
        # 获取表格数据
        table_name = "Task"
        print_log(f"正在获取表格 {table_name} 的数据...", "INFO")
        rows = base.list_rows(table_name)
        total_rows = len(rows)
        print_log(f"成功获取 {total_rows} 行数据", "SUCCESS")
        
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
            result = process_single_row(row, base, table_name, total_rows, index, history)
            
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
        
    except Exception as e:
        print_log(f"程序执行出错: {str(e)}", "ERROR")
        
if __name__ == '__main__':
    main() 