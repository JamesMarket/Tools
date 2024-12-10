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
    def __init__(self, base, upload_api):
        self.base = base
        self.storage = CustomStorage(upload_api)
        
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
        
        processed_rows = 0
        total_images = 0
        success_count = 0
        updated_rows = 0
        
        # 分页处理，每页1000条
        page_size = 1000
        start = 0
        
        while True:
            # 获取当前页的数据
            rows = self.base.list_rows(table_name, start=start, limit=page_size)
            if not rows:
                break
            
            current_page = start // page_size + 1
            print(f"\n处理第 {current_page} 页数据，本页 {len(rows)} 条记录")
            
            for row in rows:
                processed_rows += 1
                row_id = row['_id']
                images = row.get(image_column_name, [])
                
                if not images:
                    continue
                    
                new_images = []
                updated = False
                
                print(f"处理行 {row_id} 的图片... (已处理 {processed_rows} 行)")
                
                # 确保images是列表
                if isinstance(images, str):
                    images = [images]
                
                for index, image in enumerate(images, 1):
                    # 检查是否已经是自定义图床链接
                    if isinstance(image, dict):
                        image_url = image.get('url', '')
                    else:
                        image_url = image
                    
                    # 只处理 SeaTable 的图片
                    if not 'seatable.cn' in image_url:
                        print(f"图片 {index} 不是SeaTable图片，跳过")
                        new_images.append(image)
                        continue
                        
                    if 'img.shuang.fun' in image_url:
                        print(f"图片 {index} 已经在图床中，跳过")
                        new_images.append(image)
                        continue
                    
                    total_images += 1
                    
                    # 下载原图片
                    print(f"下载图片 {index}...")
                    temp_file_path = self.download_image(image_url)
                    if not temp_file_path:
                        print(f"图片 {index} 下载失败，保持原链接")
                        new_images.append(image)
                        continue
                    
                    # 上传到图床
                    print(f"上传图片 {index} 到自定义图床...")
                    new_url = self.storage.upload_to_custom_storage(temp_file_path)
                    if new_url:
                        # 成功转存后，不保留���文件信息，只使用新URL
                        new_images.append(new_url)
                        updated = True
                        success_count += 1
                        print(f"图片 {index} 已成功转存: {new_url}")
                    else:
                        print(f"图片 {index} 上传失败，保持原链接")
                        new_images.append(image)
                    
                    # 删除临时文件
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                    
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
                        updated_rows += 1
                    except Exception as e:
                        print(f"更新行 {row_id} 失败: {str(e)}")
            
            # 更新起始位置，获取下一页数据
            start += len(rows)  # 使用实际获取的行数
            if len(rows) < page_size:  # 如果获取的行数小于页大小，说明已经是最后一页
                break
        
        print(f"\n处理完成！")
        print(f"总计处理行数: {processed_rows} 行")
        print(f"包含图片的行数: {updated_rows} 行")
        print(f"总计处理图片: {total_images} 张")
        print(f"成功转存: {success_count} 张")
        print(f"失败: {total_images - success_count} 张")

def main():
    # 使用SeaTable脚本环境的base对象
    server_url = context.server_url  # 这个会自动获取
    api_token = context.api_token    # 这个会自动获取
    base = Base(api_token, server_url)
    base.auth()  # 进行认证
    
    upload_api = 'https://img.shuang.fun/api/tgchannel'
    
    # 获取当前表格名称
    table_name = context.current_table
    if not table_name:
        print("无法获取当前表格名称")
        return
        
    # 获取表格的列信息
    try:
        metadata = base.get_metadata()
        for table in metadata.get('tables', []):
            if table['name'] == table_name:
                # 获取图片列
                image_columns = [col['name'] for col in table.get('columns', []) if col.get('type') == 'image']
                if not image_columns:
                    print(f"表格 {table_name} 中没有图片列")
                    return
                    
                print(f"发现图片列: {', '.join(image_columns)}")
                
                # 处理每个图片列
                processor = ImageProcessor(base, upload_api)
                for column_name in image_columns:
                    print(f"\n开始处理列: {column_name}")
                    processor.process_table_images(table_name, column_name)
                return
                
        print(f"未找到表格: {table_name}")
    except Exception as e:
        print(f"获取表格信息失败: {str(e)}")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"程序出错: {str(e)}")
    finally:
        print("\n程序结束") 