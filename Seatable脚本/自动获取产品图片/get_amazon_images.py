from seatable_api import Base
import requests
import re
import time
import json

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

def get_amazon_image(url):
    """
    从亚马逊产品页面获取主图片URL
    """
    print(f"正在处理链接: {url}")
    
    # 获取站点信息
    domain, site = get_amazon_domain(url)
    print(f"站点: {site} ({domain})")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': f'https://{domain}/'
    }
    
    try:
        # 获取页面内容
        response = requests.get(url, headers=headers, timeout=10)
        print(f"请求状态码: {response.status_code}")
        
        if response.status_code != 200:
            print("页面请求失败")
            return None
            
        content = response.text
        
        # 1. 首先尝试从data-a-dynamic-image中获取（通常包含最高质量的图片）
        dynamic_image_match = re.search(r'data-a-dynamic-image="([^"]+)"', content)
        if dynamic_image_match:
            try:
                image_dict = json.loads(dynamic_image_match.group(1).replace('&quot;', '"'))
                # 获取最大尺寸的图片URL
                largest_image = max(image_dict.items(), key=lambda x: int(x[1][0]) * int(x[1][1]))
                image_url = largest_image[0]
                print(f"找到动态图片URL: {image_url}")
                return image_url
            except:
                pass
        
        # 2. 尝试其他图片URL模式
        image_patterns = [
            # 高清图片URL
            r'data-old-hires="(https://[^"]+)"',
            r'data-zoom-hires="(https://[^"]+)"',
            # 主图片URL
            r'id="landingImage"[^>]+src="(https://[^"]+)"',
            r'id="imgBlkFront"[^>]+src="(https://[^"]+)"',
            # 产品图片URL
            r'"large":"(https://[^"]+\.jpg)"',
            r'"main":"(https://[^"]+\.jpg)"',
            # 备用图片URL
            r'data-a-image-name="[^"]*"[^>]*src="(https://[^"]+)"',
            r'id="main-image"[^>]+src="(https://[^"]+)"',
            # 其他可能的图片URL
            r'"hiRes":"(https://[^"]+)"',
            r'"thumb":"(https://[^"]+)"'
        ]
        
        for pattern in image_patterns:
            matches = re.findall(pattern, content)
            if matches:
                image_url = matches[0].replace('\\', '')  # 移除可能的转义字符
                
                # 确保获取高清图片
                if '_SL1500_' not in image_url and '._AC_' in image_url:
                    image_url = image_url.replace('._AC_', '._AC_SL1500_')
                elif '_SX' in image_url:
                    image_url = re.sub(r'\._SX\d+_', '._SX1500_', image_url)
                
                print(f"找到图片URL: {image_url}")
                return image_url
                
        print("未找到图片URL")
        return None
    except Exception as e:
        print(f"获取图片时出错: {str(e)}")
        return None

def main():
    server_url = 'https://cloud.seatable.cn'
    api_token = '6bb4ff858146274941bbcd693b9d837d054d16b3'
    
    print("正在连接到SeaTable...")
    base = Base(api_token, server_url)
    base.auth()  # 进行身份验证
    print("SeaTable认证成功")
    
    # 获取表格数据
    table_name = "测评任务"  # 替换为您的表格名称
    print(f"正在获取表格 {table_name} 的数据...")
    rows = base.list_rows(table_name)
    print(f"获取到 {len(rows)} 行数据")
    
    # 处理统计
    total = len(rows)
    updated = 0
    skipped = 0
    failed = 0
    
    for index, row in enumerate(rows, 1):
        print(f"\n处理第 {index}/{total} 行数据:")
        product_url = row.get('产品链接')
        print(f"产品链接: {product_url}")
        
        if not product_url:
            print("产���链接为空，跳过")
            skipped += 1
            continue
        
        # 获取当前的图片URL
        current_image = row.get('产品图片')
        current_image_url = None
        if current_image and isinstance(current_image, list) and len(current_image) > 0:
            current_image_url = current_image[0]
            print(f"当前图片URL: {current_image_url}")
            
        # 获取新的图片URL
        new_image_url = get_amazon_image(product_url)
        if not new_image_url:
            print("未获取到新图片URL，保持原图片不变")
            if current_image_url:
                print("保留原有图片")
                skipped += 1
            else:
                print("无原有图片")
                failed += 1
            continue
            
        # 比较新旧图片URL
        if current_image_url == new_image_url:
            print("图片URL未变化，跳过更新")
            skipped += 1
            continue
            
        # 更新产品图片列
        row_id = row['_id']
        print(f"正在更新行 {row_id} 的产品图片...")
        try:
            base.update_row(table_name, row_id, {'产品图片': [new_image_url]})
            print(f"成功更新行 {row_id} 的产品图片")
            updated += 1
        except Exception as e:
            print(f"更新行 {row_id} 时出错: {str(e)}")
            if current_image_url:
                print("保留原有图片")
                skipped += 1
            else:
                failed += 1
        
        # 添加延时避免请求过快
        if index < total:
            print("等待2秒后处理下一行...")
            time.sleep(2)
    
    # 输出最终统计
    print("\n" + "="*50)
    print("执行完成！统计信息：")
    print(f"总数: {total}")
    print(f"更新: {updated}")
    print(f"跳过: {skipped} (包含保留原图片的情况)")
    print(f"失败: {failed} (仅包含无图片的情况)")
    print("="*50)

if __name__ == '__main__':
    main() 