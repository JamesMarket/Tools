# 此文件是最终可用的稳定版本
# 主要功能：
# 1. 自动扫描SeaTable中所有表格的图片列
# 2. 将图片上传到指定的图床(img.shuang.fun)
# 3. 使用状态跟踪列记录处理进度
# 4. 每次运行限制处理15张图片
# 5. 包含完整的错误处理和日志输出

from seatable_api import Base, context
import requests
import os
import time
from urllib.parse import urlparse
import json
import tempfile

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
            
            # 发送上传请求
            response = requests.post(
                self.upload_api,
                files=files,
                timeout=30
            )
            
            # 关闭文件
            files['file'].close()
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get('url'):
                        return result.get('url')
                    else:
                        print(f"上传失败: {result.get('message', '未知错误')}")
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
        self.max_images_per_run = 15  # 每次运行最多处理15张图片
        self.processed_count = 0
        
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

    def process_table_images(self, table_name, image_column_name):
        """处理表格的图片"""
        print(f"开始处理表格 {table_name} 中的图片...")
        
        # 确保存在进度跟踪列
        self.ensure_progress_column(table_name)
        
        processed_rows = 0
        total_images = 0
        success_count = 0
        updated_rows = 0
        
        try:
            # 获取所有待处理的行
            rows = self.base.filter_rows(table_name, "图片处理状态", "待处理")
            
            if not rows:
                print("没有待处理的行")
                return
                
            for row in rows:
                if self.processed_count >= self.max_images_per_run:
                    print(f"\n已达到本次运行的最大处理数量 ({self.max_images_per_run}张图片)")
                    return
                    
                processed_rows += 1
                row_id = row['_id']
                images = row.get(image_column_name, [])
                
                if not images:
                    self.update_row_status(table_name, row_id, "已完成")
                    continue
                    
                new_images = []
                updated = False
                
                print(f"处理行 {row_id} 的图片...")
                
                # 确保images是列表
                if isinstance(images, str):
                    images = [images]
                
                for index, image in enumerate(images, 1):
                    if self.processed_count >= self.max_images_per_run:
                        break
                        
                    # 检查是否已经是自定义图床链接
                    if isinstance(image, dict):
                        image_url = image.get('url', '')
                    else:
                        image_url = image
                    
                    if 'img.shuang.fun' in image_url:
                        new_images.append(image)
                        continue
                    
                    total_images += 1
                    self.processed_count += 1
                    
                    temp_file_path = self.download_image(image_url)
                    if not temp_file_path:
                        new_images.append(image)
                        continue
                    
                    new_url = self.storage.upload_to_custom_storage(temp_file_path)
                    if new_url:
                        new_images.append(new_url)
                        updated = True
                        success_count += 1
                    else:
                        new_images.append(image)
                    
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                    
                    time.sleep(1)
                
                if updated:
                    try:
                        self.base.update_row(
                            table_name,
                            row_id,
                            {
                                image_column_name: new_images,
                                '图片处理状态': '已完成'
                            }
                        )
                        updated_rows += 1
                    except Exception as e:
                        print(f"更新行 {row_id} 失败: {str(e)}")
                else:
                    # 如果没有更新图片，也标记为已完成
                    self.update_row_status(table_name, row_id, "已完成")
            
            print(f"\n本次处理完成！")
            print(f"处理行数: {processed_rows} 行")
            print(f"更新行数: {updated_rows} 行")
            print(f"处理图片: {total_images} 张")
            print(f"成功转存: {success_count} 张")
            print(f"失败: {total_images - success_count} 张")
            
        except Exception as e:
            print(f"处理表格数据时发生错误: {str(e)}")

    def ensure_progress_column(self, table_name):
        """确保表格中存在进度跟踪列"""
        try:
            metadata = self.base.get_metadata()
            table = next((t for t in metadata['tables'] if t['name'] == table_name), None)
            if table:
                columns = table.get('columns', [])
                if not any(col['name'] == '图片处理状态' for col in columns):
                    # 添加进度列
                    self.base.insert_column(table_name, '图片处理状态', 'single-select', 
                                         options=['待处理', '已完成'])
                    # 将所有行设置为待处理
                    rows = self.base.list_rows(table_name)
                    for row in rows:
                        self.update_row_status(table_name, row['_id'], '待处理')
        except Exception as e:
            print(f"确保进度列失败: {str(e)}")

    def update_row_status(self, table_name, row_id, status):
        """更新行的处理状态"""
        try:
            self.base.update_row(table_name, row_id, {'图片处理状态': status})
        except Exception as e:
            print(f"更新行状态失败: {str(e)}")

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
        
    print("\n开始扫描表格...")
    
    # 遍历所有表格
    for table_name, columns in tables:
        image_columns = processor.get_image_columns(columns)
        
        if not image_columns:
            continue
            
        print(f"\n处理表格: {table_name}")
        print(f"发现图片列: {', '.join(image_columns)}")
        
        for column_name in image_columns:
            print(f"\n开始处理列: {column_name}")
            processor.process_table_images(table_name, column_name)
            
            if processor.processed_count >= processor.max_images_per_run:
                print("\n已达到本次���行的最大处理数量，将在下次运行继续处理")
                return

if __name__ == '__main__':
    main()