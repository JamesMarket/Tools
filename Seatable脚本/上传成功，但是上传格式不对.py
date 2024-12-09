from seatable_api import Base, context
import requests
import os
import time
from urllib.parse import urlparse
import json
import tempfile
from datetime import datetime

class CustomStorage:
    def __init__(self, upload_api):
        self.upload_api = upload_api

    def upload_to_custom_storage(self, temp_file_path):
        """上传图片到自定义图床"""
        try:
            # 检查文件大小
            file_size = os.path.getsize(temp_file_path)
            if file_size > 5 * 1024 * 1024:  # 5MB
                print(f"文件大小超过5MB限制: {file_size / 1024 / 1024:.2f}MB")
                return None
            
            # 直接使用下载的文件
            files = {
                'file': open(temp_file_path, 'rb')
            }
            
            print(f"正在发送请求到: {self.upload_api}")
            
            # 发送上传请求
            response = requests.post(
                self.upload_api,
                files=files,
                timeout=30
            )
            
            # 关闭文件
            files['file'].close()
            
            print(f"服务器状态码: {response.status_code}")
            print(f"服务器响应内容: {response.text}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
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
            
    def get_columns_with_images(self, columns):
        """获取可能包含图片的列"""
        image_columns = []
        for col in columns:
            col_type = col.get('type')
            # 只处理图片列和长文本列
            if col_type in ['image', 'long-text']:
                image_columns.append({
                    'name': col['name'],
                    'type': col_type
                })
        return image_columns
        
    def download_image(self, image_url):
        """下载图片"""
        try:
            # 从URL获取文件扩展名
            ext = os.path.splitext(urlparse(image_url).path)[1]
            if not ext:
                ext = '.jpg'  # 默认扩展名
            
            # 创建临时文件，保留扩展名
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            temp_file.close()
            
            # 使用SeaTable API下载文件到临时文件
            self.base.download_file(image_url, temp_file.name)
            
            # 检查文件是否下载成功和大小限制
            if os.path.exists(temp_file.name):
                file_size = os.path.getsize(temp_file.name)
                if file_size > 5 * 1024 * 1024:  # 5MB
                    print(f"文件大小超过5MB限制: {file_size / 1024 / 1024:.2f}MB")
                    os.unlink(temp_file.name)
                    return None
                if file_size > 0:
                    return temp_file.name
            
            print(f"下载图片失败")
            return None
        except Exception as e:
            print(f"下载图片失败: {str(e)}")
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            return None

    def process_table_images(self, table_name, column_info):
        """处理表格的图片"""
        column_name = column_info['name']
        column_type = column_info['type']
        print(f"开始处理表格 {table_name} 中的列 {column_name}...")
        
        # 构建查询条件
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_str = today.strftime('%Y-%m-%d %H:%M:%S')
        
        # 使用正确的查询语法
        query = f"_mtime >= '{today_str}'"  # 使用字符串格式的查询条件
        
        print(f"处理 {today_str} 之后更新的数据")
        
        processed_rows = 0
        total_images = 0
        success_count = 0
        updated_rows = 0
        
        # 分页处理，每页1000条
        page_size = 1000
        start = 0
        
        while True:
            try:
                # 使用正确的API方法
                rows = self.base.filter_rows(
                    table_name,
                    query,
                    start=start,
                    limit=page_size
                )
                if not rows:
                    break
                
                for row in rows:
                    processed_rows += 1
                    row_id = row['_id']
                    
                    if column_type == 'image':
                        # 处理图片列
                        images = row.get(column_name, [])
                        if isinstance(images, str):
                            images = [images]
                    else:
                        # 处理富文本列
                        content = row.get(column_name, '')
                        images = self.extract_images_from_text(content)
                    
                    if not images:
                        continue
                    
                    new_images = []
                    updated = False
                    
                    print(f"处理行 {row_id} 的图片... (已处理 {processed_rows} 行)")
                    
                    for index, image in enumerate(images, 1):
                        # 对于富文本image就是URL字符串
                        image_url = image.get('url', '') if isinstance(image, dict) else image
                        
                        if 'img.shuang.fun' in image_url:
                            print(f"图片 {index} 已经在图床中，跳过")
                            new_images.append(image)
                            continue
                        
                        total_images += 1
                        
                        # 下载和上传处理...（保持原有逻辑）
                        temp_file_path = self.download_image(image_url)
                        if not temp_file_path:
                            new_images.append(image)
                            continue
                        
                        new_url = self.storage.upload_to_custom_storage(temp_file_path)
                        if new_url:
                            if column_type == 'image':
                                new_images.append(new_url)
                            else:
                                # 替换富文本中的图��URL
                                content = content.replace(image_url, new_url)
                            updated = True
                            success_count += 1
                        else:
                            new_images.append(image)
                        
                        if os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)
                        
                        time.sleep(1)
                    
                    if updated:
                        try:
                            update_data = {
                                column_name: content if column_type != 'image' else new_images
                            }
                            self.base.update_row(table_name, row_id, update_data)
                            updated_rows += 1
                        except Exception as e:
                            print(f"更新行 {row_id} 失败: {str(e)}")
                
                start += len(rows)
                if len(rows) < page_size:
                    break
                
            except Exception as e:
                print(f"查询数据失败: {str(e)}")
                break
        
        print(f"\n处理完成！")
        print(f"总计处理行数: {processed_rows} 行")
        print(f"包含图���的行数: {updated_rows} 行")
        print(f"总计处理图片: {total_images} 张")
        print(f"成功转存: {success_count} 张")
        print(f"失败: {total_images - success_count} 张")

    def extract_images_from_text(self, text):
        """从富文本中提取图片URL"""
        if not text:
            return []
        
        # 使用正则表达式匹配图片URL
        import re
        # 匹配markdown格式的图片
        markdown_pattern = r'!\[.*?\]\((.*?)\)'
        # 匹配HTML格式的图片
        html_pattern = r'<img.*?src=[\'"](.*?)[\'"].*?>'
        
        urls = []
        # 查找所有markdown格式的图片
        urls.extend(re.findall(markdown_pattern, text))
        # 查找所有HTML格式的图片
        urls.extend(re.findall(html_pattern, text))
        
        return list(set(urls))  # 去重

    def get_files_from_workspace(self):
        """获取工作区中的所有图片文件"""
        try:
            # 使用正确的API方法
            files = self.base.get_file_list()  # 使用 get_file_list 方法
            image_files = []
            for file in files:
                file_name = file.get('name', '').lower()
                if any(file_name.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                    image_files.append(file)
            return image_files
        except Exception as e:
            print(f"获取工作区文件失败: {str(e)}")
            return []

    def process_workspace_images(self):
        """处理工作区中的图片"""
        print("开始处理工作区中的图片...")
        
        # 获取所有图片文件
        image_files = self.get_files_from_workspace()
        if not image_files:
            print("未找到图片文件")
            return
            
        print(f"找到 {len(image_files)} 个图片文件")
        
        total_files = len(image_files)
        success_count = 0
        
        for index, file in enumerate(image_files, 1):
            file_name = file.get('name')
            file_url = file.get('url')
            
            print(f"\n处理文件 {index}/{total_files}: {file_name}")
            
            # 下载图片
            temp_file_path = self.download_image(file_url)
            if not temp_file_path:
                print(f"下载文件 {file_name} 失败，跳过")
                continue
            
            # 上传到图床
            new_url = self.storage.upload_to_custom_storage(temp_file_path)
            if new_url:
                print(f"文件 {file_name} 已成功转存到图床")
                success_count += 1
                
                # 删除原文件
                try:
                    self.base.delete_file(file_name)  # 使用 delete_file 方法
                    print(f"已删除原文件 {file_name}")
                except Exception as e:
                    print(f"删除原文件 {file_name} 失败: {str(e)}")
            else:
                print(f"上传文件 {file_name} 到图床失败")
            
            # 清理临时文件
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            
            # 避免请求过于频繁
            time.sleep(1)
        
        print(f"\n处理完成！")
        print(f"总计处理文件: {total_files} 个")
        print(f"成功转存: {success_count} 个")
        print(f"失败: {total_files - success_count} 个")

def main():
    server_url = context.server_url or 'https://cloud.seatable.cn'
    api_token = context.api_token or 'your_api_token'
    upload_api = 'https://img.shuang.fun/api/tgchannel'
    
    processor = ImageProcessor(api_token, server_url, upload_api)
    
    # 处理工作区文件
    print("\n开始处理工作区文件...")
    processor.process_workspace_images()
    
    # 处理表格中的图片列
    print("\n开始处理表格...")
    tables = processor.get_tables()
    if not tables:
        print("未找到任何表格，请检查权限和连接状态")
        return
    
    # 遍历所有表格
    for table_name, columns in tables:
        # 获取可能包含图片的列
        image_columns = processor.get_columns_with_images(columns)
        
        if not image_columns:
            print(f"\n表格 {table_name} 没有可能包含图片的列，跳过")
            continue
            
        print(f"\n处理表格: {table_name}")
        print(f"发现可能包含图片的列: {', '.join(col['name'] for col in image_columns)}")
        
        # 处理每个列
        for column_info in image_columns:
            print(f"\n开始处理列: {column_info['name']} (类型: {column_info['type']})")
            try:
                processor.process_table_images(table_name, column_info)
            except Exception as e:
                print(f"处理表格 {table_name} 的列 {column_info['name']} 时发生错误: {str(e)}")
                continue
    
    print("\n所有表格处理完成！")

if __name__ == '__main__':
    main()