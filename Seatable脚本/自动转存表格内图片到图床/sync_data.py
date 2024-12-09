from seatable_api import Base, context
import requests
import os
import time
from urllib.parse import urlparse
import json

class CustomStorage:
    def __init__(self, upload_api):
        self.upload_api = upload_api

    def upload_to_custom_storage(self, image_data):
        """上传图片到自定义图床"""
        try:
            # 准备表单数据
            files = {
                'file': image_data
            }
            
            print(f"正在发送请求到: {self.upload_api}")
            
            # 发送上传请求
            response = requests.post(
                self.upload_api,
                files=files,
                timeout=30
            )
            
            print(f"服务器响应状态码: {response.status_code}")
            print(f"服务器响应内容: {response.text}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    # 从响应中提取url字段，直接使用原始URL
                    if result.get('url'):
                        return result.get('url')
                    else:
                        error_msg = result.get('message', '未知错误')
                        print(f"上传失败: {error_msg}")
                        return None
                except json.JSONDecodeError as e:
                    print(f"解析响应JSON失败: {str(e)}")
                    return None
            else:
                print(f"上传失败: HTTP状态码 {response.status_code}")
                return None
        except requests.exceptions.Timeout:
            print("上传超时，请检查网络连接")
            return None
        except requests.exceptions.RequestException as e:
            print(f"请求异常: {str(e)}")
            return None
        except Exception as e:
            print(f"上传过程发生错误: {str(e)}")
            return None

class ImageProcessor:
    def __init__(self, api_token, server_url, upload_api):
        self.base = Base(api_token, server_url)
        self.base.auth()
        self.storage = CustomStorage(upload_api)
        
    def get_tables(self):
        """获取所有可用的表格列表"""
        try:
            metadata = self.base.get_metadata()
            tables = metadata.get('tables', [])
            return [(table['name'], table.get('columns', [])) for table in tables]
        except Exception as e:
            print(f"获取表格列表失败: {str(e)}")
            return []
            
    def get_image_columns(self, columns):
        """获取表格中的图片类型列"""
        return [col['name'] for col in columns if col.get('type') == 'image']
        
    def download_image(self, image_url):
        """下载图片"""
        try:
            response = requests.get(image_url)
            if response.status_code == 200:
                return response.content
            print(f"下载图片失败: HTTP状态码 {response.status_code}")
            return None
        except Exception as e:
            print(f"下载图片失败: {str(e)}")
            return None

    def process_table_images(self, table_name, image_column_name):
        """处理表格中的图片"""
        print(f"开始处理表格 {table_name} 中的图片...")
        rows = self.base.list_rows(table_name)
        
        total_images = 0
        success_count = 0
        
        for row in rows:
            row_id = row['_id']
            images = row.get(image_column_name, [])
            
            if not images:
                continue
                
            new_images = []
            updated = False
            
            print(f"处理行 {row_id} 的图片...")
            
            # 确保images是列表
            if isinstance(images, str):
                images = [images]
            
            for index, image in enumerate(images, 1):
                # 检查是否已经是自定义图床链接
                if isinstance(image, dict):
                    image_url = image.get('url', '')
                else:
                    image_url = image
                
                if 'img.shuang.fun' in image_url:
                    print(f"图片 {index} 已经在目标图床中，跳过")
                    new_images.append(image)
                    continue
                
                total_images += 1
                
                # 下载原图片
                print(f"下载图片 {index}...")
                image_data = self.download_image(image_url)
                if not image_data:
                    print(f"图片 {index} 下载失败，保持原链接")
                    new_images.append(image)
                    continue
                
                # 上传到图床
                print(f"上传图片 {index} 到自定义图床...")
                new_url = self.storage.upload_to_custom_storage(image_data)
                if new_url:
                    if isinstance(image, dict):
                        new_images.append({
                            'name': image.get('name', ''),
                            'url': new_url,
                            'size': len(image_data)
                        })
                    else:
                        new_images.append(new_url)
                    updated = True
                    success_count += 1
                    print(f"图片 {index} 已成功转存: {new_url}")
                else:
                    print(f"图片 {index} 上传失败，保持原链接")
                    new_images.append(image)
                
                # 避免请求过于频繁
                time.sleep(1)
            
            if updated:
                # 更新行数据
                try:
                    self.base.update_row(
                        table_name,
                        row_id,
                        {image_column_name: new_images}
                    )
                    print(f"行 {row_id} 更新成功")
                except Exception as e:
                    print(f"更新行 {row_id} 失败: {str(e)}")
        
        print(f"\n处理完成！")
        print(f"总计处理图片: {total_images} 张")
        print(f"成功转存: {success_count} 张")
        print(f"失败: {total_images - success_count} 张")

def main():
    server_url = context.server_url or 'https://cloud.seatable.cn'
    api_token = context.api_token or 'your_api_token'
    upload_api = 'https://img.shuang.fun/api/tgchannel'
    
    processor = ImageProcessor(api_token, server_url, upload_api)
    
    # 获取所有表格和列信息
    tables = processor.get_tables()
    if not tables:
        print("未找到任何表格，请检查权限和连接状态")
        return
        
    print("\n开始扫描所有表格...")
    
    # 遍历所有表格
    for table_name, columns in tables:
        # 获取表格中的图片列
        image_columns = processor.get_image_columns(columns)
        
        if not image_columns:
            print(f"\n表格 {table_name} 中没有图片列，跳过")
            continue
            
        print(f"\n处理表格: {table_name}")
        print(f"发现图片列: {', '.join(image_columns)}")
        
        # 处理每个图片列
        for column_name in image_columns:
            print(f"\n开始处理列: {column_name}")
            try:
                processor.process_table_images(table_name, column_name)
            except Exception as e:
                print(f"处理表格 {table_name} 的列 {column_name} 时发生错误: {str(e)}")
                continue
    
    print("\n所有表格处理完成！")

if __name__ == '__main__':
    main()