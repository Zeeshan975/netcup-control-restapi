import os
import time
from qbittorrentapi import Client
from logger import logger

class QBittorrentClient:
    """
    使用 qbittorrent-api 实现的精简版客户端，添加了种子状态检查功能和排除分类功能。
    """
    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        exclude_categories: list[str] | None = None,
    ):
        """
        初始化客户端，自动从环境变量中加载配置。
        
        Args:
            url: qBittorrent WebUI URL
            username: 用户名
            password: 密码
            exclude_categories: 排除的分类列表，这些分类的种子不会被操作
        """
        self.host = url
        self.username = username
        self.password = password
        self.exclude_categories = set(exclude_categories or [])
        
        try:
            self.client = Client(
                host=self.host, 
                username=self.username, 
                password=self.password, 
                VERIFY_WEBUI_CERTIFICATE=False
            )
            self.client.auth_log_in()
            logger.info(f"成功连接到 qBittorrent API: {self.host}")
            if self.exclude_categories:
                logger.info(f"排除分类: {', '.join(self.exclude_categories)}")
        except Exception as e:
            raise ConnectionError(f"连接 qBittorrent API 失败: {e}")
    
    def _get_filterable_torrents(self) -> list:
        """
        获取所有可操作的种子（排除指定分类）
        
        Returns:
            不在排除分类中的种子列表
        """
        try:
            all_torrents = self.client.torrents.info()
            
            if not self.exclude_categories:
                return all_torrents
            
            # 过滤掉排除分类的种子
            filterable = []
            excluded_count = 0
            
            for torrent in all_torrents:
                category = torrent.category or ""
                if category in self.exclude_categories:
                    excluded_count += 1
                    logger.debug(f"排除种子: {torrent.name[:50]} (分类: {category})")
                else:
                    filterable.append(torrent)
            
            if excluded_count > 0:
                logger.info(f"共排除 {excluded_count} 个种子（属于排除分类）")
                logger.info(f"可操作种子数: {len(filterable)}")
            
            return filterable
            
        except Exception as e:
            logger.error(f"获取种子列表失败: {e}")
            return []
    
    def _get_hashes(self, torrents: list) -> list[str]:
        """从种子列表中提取hash"""
        return [t.hash for t in torrents]
    
    def is_alive(self) -> bool:
        """简易健康检查：尝试请求应用版本。"""
        try:
            ver = self.client.app.version
            logger.info(f"{self.host} app version is {ver}")
            return True
        except Exception:
            return False
    
    def reannounce_all(self):
        """
        强制所有种子向tracker汇报（排除指定分类）。
        """
        try:
            torrents = self._get_filterable_torrents()
            if not torrents:
                logger.info("没有可汇报的种子")
                return
            
            hashes = self._get_hashes(torrents)
            self.client.torrents.reannounce(hashes=hashes)
            logger.info(f"已发出强制汇报指令，共 {len(hashes)} 个种子")
            # 等待一段时间让汇报完成
            time.sleep(2)
        except Exception as e:
            logger.error(f"强制汇报失败: {e}")
            
    def pause_all(self):
        """
        暂停所有种子任务（排除指定分类）。
        """
        try:
            torrents = self._get_filterable_torrents()
            if not torrents:
                logger.info("没有可暂停的种子")
                return
            
            hashes = self._get_hashes(torrents)
            self.client.torrents.pause(hashes=hashes)
            logger.info(f"已发出暂停指令，共 {len(hashes)} 个种子")
        except Exception as e:
            logger.error(f"暂停种子失败: {e}")
    
    def pause_all_with_reannounce(self):
        """
        先强制汇报，再暂停所有种子任务（排除指定分类）。
        """
        logger.info("开始执行：强制汇报 -> 暂停种子")
        
        # 1. 强制汇报
        self.reannounce_all()
        
        # 2. 暂停所有种子
        self.pause_all()
        
        logger.info("完成：种子已汇报并暂停")
            
    def delete_all(self, *, delete_files: bool = False) -> None:
        """
        删除全部任务（排除指定分类）。
        
        Args:
            delete_files: True 时会连同本地数据一并删除（危险操作）
        """
        try:
            torrents = self._get_filterable_torrents()
            if not torrents:
                logger.info("没有可删除的种子")
                return
            
            hashes = self._get_hashes(torrents)
            self.client.torrents.delete(hashes=hashes, delete_files=delete_files)
            action = "删除种子和文件" if delete_files else "删除种子(保留文件)"
            logger.info(f"已发出删除指令，共 {len(hashes)} 个种子 - {action}")
        except Exception as e:
            logger.error(f"删除种子失败: {e}")

    def resume_all(self):
        """恢复所有暂停的种子（排除指定分类）"""
        try:
            torrents = self._get_filterable_torrents()
            if not torrents:
                logger.info("没有可恢复的种子")
                return
            
            hashes = self._get_hashes(torrents)
            self.client.torrents.resume(hashes=hashes)
            logger.info(f"已发出恢复指令，共 {len(hashes)} 个种子")
        except Exception as e:
            logger.error(f"恢复种子失败: {e}")

    def pause_and_delete_all(self, *, delete_files: bool = False) -> None:
        """
        先强制汇报，再暂停，最后删除所有任务（排除指定分类）。
        
        Args:
            delete_files: True 时会连同本地数据一并删除（危险操作）
        """
        logger.info("开始执行：强制汇报 -> 暂停 -> 删除种子")
        
        # 1. 强制汇报
        self.reannounce_all()
        
        # 2. 暂停所有种子
        self.pause_all()
        
        # 3. 等待一下确保暂停完成
        time.sleep(1)
        
        # 4. 删除所有种子
        self.delete_all(delete_files=delete_files)
        
        logger.info("完成：种子已汇报、暂停并删除")
    
    def get_statistics(self) -> dict:
        """
        获取种子统计信息
        
        Returns:
            包含总数、排除数、可操作数的字典
        """
        try:
            all_torrents = self.client.torrents.info()
            filterable = self._get_filterable_torrents()
            
            return {
                "total": len(all_torrents),
                "excluded": len(all_torrents) - len(filterable),
                "operable": len(filterable),
                "exclude_categories": list(self.exclude_categories)
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                "total": 0,
                "excluded": 0,
                "operable": 0,
                "exclude_categories": list(self.exclude_categories)
            }