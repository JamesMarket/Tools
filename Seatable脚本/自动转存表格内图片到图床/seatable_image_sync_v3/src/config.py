import os
import json
import logging
from typing import Dict, Any, List

class Config:
    def __init__(self):
        """初始化配置"""
        self.config = self._load_from_env()
        self.setup_logging()

    def _parse_base_tokens(self, tokens_str: str) -> List[Dict[str, str]]:
        """解析base tokens
        格式: [{"name": "base1", "token": "token1"}, {"name": "base2", "token": "token2"}]
        或者: token1,token2,token3
        """
        if not tokens_str:
            return []
            
        try:
            # 尝试解析JSON格式
            bases = json.loads(tokens_str)
            if isinstance(bases, list):
                return bases
        except json.JSONDecodeError:
            # 如果不是JSON格式，则按逗号分隔处理
            tokens = [t.strip() for t in tokens_str.split(',') if t.strip()]
            return [{'token': token} for token in tokens]
            
        return []

    def _load_from_env(self) -> Dict[str, Any]:
        """从环境变量加载配置"""
        # 获取并解析base tokens
        base_tokens_str = os.getenv('SEATABLE_API_TOKENS') or os.getenv('SEATABLE_API_TOKEN')
        if not base_tokens_str:
            raise Exception("环境变量未设置: SEATABLE_API_TOKENS 或 SEATABLE_API_TOKEN")
            
        bases = self._parse_base_tokens(base_tokens_str)
        if not bases:
            raise Exception("无效的API Token配置")

        config = {
            'seatable': {
                'bases': bases,
                'server_url': os.getenv('SEATABLE_SERVER_URL', 'https://cloud.seatable.cn')
            },
            'image_bed': {
                'upload_api': os.getenv('IMAGE_BED_API', 'https://img.shuang.fun/api/tgchannel'),
                'size_limit': int(os.getenv('IMAGE_SIZE_LIMIT', '5'))  # 默认5MB
            },
            'logging': {
                'level': os.getenv('LOG_LEVEL', 'INFO'),
                'format': '%(asctime)s - %(levelname)s - %(message)s',
                'file': os.getenv('LOG_FILE', 'logs/sync.log')
            },
            'progress': {
                'save_enabled': os.getenv('SAVE_PROGRESS', 'true').lower() == 'true',
                'file': os.getenv('PROGRESS_FILE', 'logs/progress.json'),
                'save_interval': int(os.getenv('PROGRESS_SAVE_INTERVAL', '300'))
            }
        }

        return config

    def setup_logging(self) -> None:
        """设置日志"""
        log_config = self.config['logging']
        log_file = log_config['file']
        
        # 确保日志目录存在
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        # 配置日志
        logging.basicConfig(
            level=getattr(logging, log_config['level'].upper()),
            format=log_config['format'],
            handlers=[
                logging.StreamHandler(),  # 输出到控制台
                logging.FileHandler(log_file, encoding='utf-8')  # 输出到文件
            ]
        )

    def get(self, section: str, key: str = None) -> Any:
        """获取配置值"""
        if key is None:
            return self.config.get(section, {})
        return self.config.get(section, {}).get(key)

    @property
    def seatable_config(self) -> Dict[str, Any]:
        """获取SeaTable配置"""
        return self.get('seatable')

    @property
    def image_bed_config(self) -> Dict[str, Any]:
        """获取图床配置"""
        return self.get('image_bed')

    @property
    def progress_config(self) -> Dict[str, Any]:
        """获取进度保存配置"""
        return self.get('progress') 