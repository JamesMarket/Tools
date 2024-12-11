"""
SeaTable 亚马逊产品图片获取插件
在当前行获取亚马逊产品图片

注意：需要表格中有以下列：
- 产品链接：链接类型
- 产品图片：图片类型
"""

from seatable_api import context
import requests
import re
import json
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import random
import time
import tempfile
import os

def get_amazon_domain(url):
    """获取亚马逊链接的域名和站点信息"""
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
    return 'amazon.com', 'US'

def get_amazon_image(url):
    """从亚马逊产品页面获取主图片URL"""
    try:
        # 配置重试策略
        retry_strategy = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
            connect=5,
            read=5,
            redirect=10
        )

        # 创建session
        session = requests.Session()
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=1,
            pool_maxsize=1,
            pool_block=False
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # 处理URL格式
        if not url.startswith('http'):
            url = 'https://' + url
        
        # 移除URL中的跟踪参数
        url = re.sub(r'\?.*$', '', url)  # 移除所有查询参数
        url = re.sub(r'/ref=.*$', '', url)  # 移除ref参数
        url = re.sub(r'/tag=.*$', '', url)  # 移除tag参数
        
        print(f"清理后的URL: {url}")
        
        # 获取站点信息
        domain, site = get_amazon_domain(url)
        print(f"站点信息: {site} ({domain})")
        
        # 生成随机User-Agent
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
        ]
        user_agent = random.choice(user_agents)
        
        # 请求头
        headers = {
            'authority': domain,
            'method': 'GET',
            'path': url.split(domain)[1],
            'scheme': 'https',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'accept-encoding': 'gzip, deflate, br',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': user_agent,
            'referer': f'https://www.{domain}/',
            'cookie': f'session-id={random.randint(100000000, 999999999)}; session-id-time={int(time.time())}',
            'dnt': '1'
        }
        
        # 配置请求选项
        request_options = {
            'headers': headers,
            'timeout': (20, 30),
            'allow_redirects': True,
            'verify': True,
            'stream': True
        }
        
        # 添加初始延迟
        time.sleep(random.uniform(2, 4))
        
        # 获取页面内容
        print("开始请求页面...")
        
        # 首先发送一个HEAD请求
        try:
            session.head(url, headers=headers, timeout=10)
            time.sleep(random.uniform(1, 2))
        except:
            pass
        
        # 然后发送GET请求
        with session.get(url, **request_options) as response:
            if response.status_code == 301 or response.status_code == 302:
                new_url = response.headers.get('Location')
                print(f"遇到重定向，新URL: {new_url}")
                if new_url:
                    url = new_url if new_url.startswith('http') else f'https://{domain}{new_url}'
                    time.sleep(random.uniform(1, 2))
                    response = session.get(url, **request_options)
            
            if response.status_code != 200:
                print(f"页面请求失败: HTTP {response.status_code}")
                return None, f"页面请求失败: HTTP {response.status_code}"
            
            print("开始读取页面内容...")
            content = ''
            for chunk in response.iter_content(chunk_size=8192, decode_unicode=True):
                if chunk:
                    content += chunk
            
            # 检查是否是防爬虫页面
            if 'Robot Check' in content or 'captcha' in content.lower():
                print("遇到防爬虫检查")
                return None, "遇到防爬虫检查"
            
            print("页面内容获取完成，开始解析...")
            
            # 1. 尝试从data-a-dynamic-image中获取
            dynamic_image_match = re.search(r'data-a-dynamic-image="([^"]+)"', content)
            if dynamic_image_match:
                try:
                    image_dict = json.loads(dynamic_image_match.group(1).replace('&quot;', '"'))
                    largest_image = max(image_dict.items(), key=lambda x: int(x[1][0]) * int(x[1][1]))
                    print(f"从dynamic-image获取到图片: {largest_image[0]}")
                    return largest_image[0], None
                except Exception as e:
                    print(f"解析dynamic-image失败: {str(e)}")
            
            # 2. 尝试其他图片URL模式
            image_patterns = [
                # 高清图片URL
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
                r'class="a-dynamic-image"[^>]+src="(https://[^"]+)"',
                # 新增的模式
                r'<img[^>]+id="imgBlkFront"[^>]+src="([^"]+)"',
                r'<img[^>]+id="landingImage"[^>]+src="([^"]+)"',
                r'<img[^>]+data-old-hires="([^"]+)"',
                r'<img[^>]+data-a-dynamic-image="([^"]+)"',
                r'"imageUrl":"(https://[^"]+)"',
                r'"image":"(https://[^"]+)"',
                r'"thumb":"(https://[^"]+)"',
                r'"initial":"(https://[^"]+)"'
            ]
            
            print("开始匹配图片URL...")
            for pattern in image_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    for match in matches:
                        if isinstance(match, tuple):
                            match = match[0]
                        image_url = match.replace('\\', '')
                        
                        print(f"找到匹配: {image_url}")
                        
                        # 确保获取高清图片
                        if '_SL1500_' not in image_url and '._AC_' in image_url:
                            image_url = image_url.replace('._AC_', '._AC_SL1500_')
                        elif '_SX' in image_url:
                            image_url = re.sub(r'\._SX\d+_', '._SX1500_', image_url)
                        elif '_SY' in image_url:
                            image_url = re.sub(r'\._SY\d+_', '._SY1500_', image_url)
                        elif '_SR' in image_url:
                            image_url = re.sub(r'\._SR\d+,\d+_', '._SR1500,1500_', image_url)
                        
                        if 'sprite' not in image_url.lower() and 'placeholder' not in image_url.lower():
                            print(f"返回有效图片URL: {image_url}")
                            return image_url, None
            
            print("未找到任何匹配的图片URL")
            # 保存页面内容以供调试
            print("页面内容片段:")
            print(content[:500] + "...")
            return None, "未找到图片"
            
    except requests.Timeout:
        print("请求超时")
        return None, "请求超时"
    except requests.TooManyRedirects:
        print("重定向次数过多")
        return None, "重定向次数过多"
    except Exception as e:
        print(f"请求出错: {str(e)}")
        return None, f"请求出错: {str(e)}"

def get_high_quality_image(url):
    """获取高清版本的图片URL"""
    # 提取基本URL部分（移除所有尺寸参数）
    base_url = url.split('._')[0]
    # 添加高清尺寸参数
    return f"{base_url}._AC_SL1500_.jpg"

def process_row(row):
    """处理单行数据"""
    try:
        # 获取产品链接（链接类型）
        product_link = row.get('产品链接')
        if not product_link:
            print("产品链接为空")
            return False, "产品链接为空"
            
        # 从链接类型中获取URL（处理不同的链接格式）
        if isinstance(product_link, dict):
            product_url = product_link.get('url', '')
        elif isinstance(product_link, str):
            product_url = product_link
        else:
            print(f"无法处理的链接格式: {type(product_link)}")
            return False, "无法处理的链接格式"
            
        if not product_url:
            print("产品链接URL为空")
            return False, "产品链接URL为空"
            
        print(f"处理链接: {product_url}")
        
        # 获取当前图片
        current_image = row.get('产品图片', [])
        current_image_url = current_image[0] if current_image and len(current_image) > 0 else None
        if current_image_url:
            print(f"当前图片: {current_image_url}")
        
        # 获取新图片
        new_image_url, error = get_amazon_image(product_url)
        if not new_image_url:
            if current_image_url:
                print(f"获取新图片失败({error})，保留原图片")
                return False, f"获取新图片失败({error})，保留原图片"
            else:
                print(f"获取新图片失败({error})")
                return False, f"获取新图片失败({error})"
        
        # 获取高清版本
        new_image_url = get_high_quality_image(new_image_url)
        print(f"获取到新图片: {new_image_url}")
        
        # 比较新旧图���
        if current_image_url == new_image_url:
            print("图片未发生变化")
            return False, "图片未发生变化"
        
        return True, new_image_url
        
    except Exception as e:
        print(f"处理出错: {str(e)}")
        return False, f"处理出错: {str(e)}"

def download_image(url):
    """下载图片到临时文件"""
    try:
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            return None, "下载图片失败"
            
        # 创建临时文件
        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
        temp_file.close()
        
        return temp_file.name, None
    except Exception as e:
        return None, f"下载失败: {str(e)}"

def main():
    """按钮入口函数"""
    try:
        # 获取当前行数据
        row = context.current_row
        if not row:
            print("未找到当前行数据")
            return
            
        print(f"当前行数据: {row}")
        
        # 处理当前行
        success, result = process_row(row)
        
        if success:
            print(f"获取到图片URL: {result}")
            
            # 下载图片
            temp_file, error = download_image(result)
            if not temp_file:
                print(f"下载图片失败: {error}")
                return
                
            try:
                # 上传图片到 SeaTable
                with open(temp_file, 'rb') as f:
                    uploaded_url = context.upload_image(f)
                    if uploaded_url:
                        # 更新图片列
                        context.current_row['产品图片'] = [uploaded_url]
                        print(f"已更新产品图片: {uploaded_url}")
                    else:
                        print("上传图片失败")
            finally:
                # 清理临时文件
                try:
                    os.unlink(temp_file)
                except:
                    pass
            
            # 显示当前行所有数据
            print("当前行更新后的完整数据:")
            for key, value in context.current_row.items():
                print(f"{key}: {value}")
        else:
            print(f"处理失败: {result}")
            
    except Exception as e:
        print(f"脚本执行出错: {str(e)}")
        print(f"错误类型: {type(e)}")
        print(f"错误详情: {str(e)}")

# 确保入口函数被调用
main() 