import os
import time
from qbittorrentapi import Client
from logger import logger


class QBittorrentClient:
    """
    使用 qbittorrent-api 实现的精简版客户端，添加了种子状态检查和分类排除功能。
    """

    def __init__(
            self,
            url: str | None = None,
            username: str | None = None,
            password: str | None = None,
    ):
        """
        初始化客户端，自动从环境变量中加载配置。
        """
        self.host = url
        self.username = username
        self.password = password
        try:
            self.client = Client(
                host=self.host,
                username=self.username,
                password=self.password,
                VERIFY_WEBUI_CERTIFICATE=False
            )
            self.client.auth_log_in()
            logger.info(f"成功连接到 qBittorrent API: {self.host}")
        except Exception as e:
            raise ConnectionError(f"连接 qBittorrent API 失败: {e}")

    def is_alive(self) -> bool:
        """简易健康检查：尝试请求应用版本。"""
        try:
            ver = self.client.app.version
            logger.info(f"{self.host} app version is {ver}")
            return True
        except Exception:
            return False

    def _get_torrents_excluding_categories(self, exclude_categories: list[str] | None = None):
        """
        获取所有种子，但排除指定分类的种子。

        Args:
            exclude_categories: 要排除的分类列表

        Returns:
            符合条件的种子对象列表、"all" 或 None
        """
        if not exclude_categories:
            return "all"

        try:
            all_torrents = self.client.torrents.info()
            excluded_torrents = []
            included_torrents = []

            for torrent in all_torrents:
                torrent_category = torrent.category or ""

                # 检查种子分类是否在排除列表中
                if torrent_category in exclude_categories:
                    excluded_torrents.append(torrent)
                    logger.debug(f"排除种子 [{torrent.name}] - 分类: {torrent_category}")
                else:
                    included_torrents.append(torrent)

            if excluded_torrents:
                logger.info(
                    f"排除了 {len(excluded_torrents)} 个分类为 {exclude_categories} 的种子，将操作 {len(included_torrents)} 个种子")

            if not included_torrents:
                logger.warning("没有符合条件的种子需要操作")
                return None

            # 返回种子对象列表
            return included_torrents

        except Exception as e:
            logger.error(f"获取种子列表失败: {e}")
            return "all"

    def reannounce_all(self, exclude_categories: list[str] | None = None):
        """
        强制种子向tracker汇报，可排除特定分类。

        Args:
            exclude_categories: 要排除的分类列表
        """
        try:
            target_torrents = self._get_torrents_excluding_categories(exclude_categories)

            if target_torrents is None:
                logger.info("没有需要汇报的种子")
                return

            if target_torrents == "all":
                self.client.torrents_reannounce(torrent_hashes="all")
                logger.info("已发出强制汇报所有种子的指令")
            else:
                # 逐个汇报以确保成功
                success_count = 0
                for torrent in target_torrents:
                    try:
                        self.client.torrents_reannounce(torrent_hashes=torrent.hash)
                        success_count += 1
                    except Exception as e:
                        logger.warning(f"汇报种子 {torrent.name} 失败: {e}")

                logger.info(f"成功汇报 {success_count}/{len(target_torrents)} 个种子")

            # 等待一段时间让汇报完成
            time.sleep(2)
        except Exception as e:
            logger.error(f"强制汇报失败: {e}")

    def pause_all(self, exclude_categories: list[str] | None = None):
        """
        暂停种子任务，可排除特定分类。

        Args:
            exclude_categories: 要排除的分类列表
        """
        try:
            target_torrents = self._get_torrents_excluding_categories(exclude_categories)

            if target_torrents is None:
                logger.info("没有需要暂停的种子")
                return

            if target_torrents == "all":
                self.client.torrents_pause(torrent_hashes="all")
                logger.info("已发出暂停所有种子任务的指令")
            else:
                # 逐个暂停以确保成功
                success_count = 0
                for torrent in target_torrents:
                    try:
                        self.client.torrents_pause(torrent_hashes=torrent.hash)
                        success_count += 1
                        logger.debug(f"暂停种子: {torrent.name}")
                    except Exception as e:
                        logger.warning(f"暂停种子 {torrent.name} 失败: {e}")

                logger.info(f"成功暂停 {success_count}/{len(target_torrents)} 个种子")

                # 等待并验证状态
                time.sleep(2)
                self._verify_pause_status(target_torrents)

        except Exception as e:
            logger.error(f"暂停种子失败: {e}")

    def _verify_pause_status(self, torrents):
        """验证种子是否真的被暂停了"""
        try:
            paused_count = 0
            for torrent in torrents:
                # 重新获取种子信息
                updated_torrent = self.client.torrents_info(torrent_hashes=torrent.hash)
                if updated_torrent and len(updated_torrent) > 0:
                    state = updated_torrent[0].state
                    if 'paused' in state.lower():
                        paused_count += 1
                    else:
                        logger.warning(f"种子 {torrent.name} 状态为 {state}，未成功暂停")

            logger.info(f"验证结果: {paused_count}/{len(torrents)} 个种子已暂停")
        except Exception as e:
            logger.warning(f"验证暂停状态失败: {e}")

    def pause_all_with_reannounce(self, exclude_categories: list[str] | None = None):
        """
        先强制汇报，再暂停种子任务，可排除特定分类。

        Args:
            exclude_categories: 要排除的分类列表
        """
        logger.info("开始执行：强制汇报 -> 暂停种子")

        # 1. 强制汇报
        self.reannounce_all(exclude_categories=exclude_categories)

        # 2. 暂停种子
        self.pause_all(exclude_categories=exclude_categories)

        logger.info("完成：种子已汇报并暂停")

    def delete_all(self, *, delete_files: bool = False, exclude_categories: list[str] | None = None) -> None:
        """
        删除任务，可排除特定分类。

        Args:
            delete_files: True 时会连同本地数据一并删除（危险操作）
            exclude_categories: 要排除的分类列表
        """
        try:
            target_torrents = self._get_torrents_excluding_categories(exclude_categories)

            if target_torrents is None:
                logger.info("没有需要删除的种子")
                return

            if target_torrents == "all":
                self.client.torrents_delete(delete_files=delete_files, torrent_hashes="all")
                logger.info("已发出删除全部任务的指令")
            else:
                # 逐个删除以确保成功
                success_count = 0
                action = "删除种子和文件" if delete_files else "删除种子(保留文件)"

                for torrent in target_torrents:
                    try:
                        self.client.torrents_delete(
                            delete_files=delete_files,
                            torrent_hashes=torrent.hash
                        )
                        success_count += 1
                        logger.debug(f"{action}: {torrent.name}")
                    except Exception as e:
                        logger.warning(f"删除种子 {torrent.name} 失败: {e}")

                logger.info(f"成功{action} {success_count}/{len(target_torrents)} 个任务")

                # 验证删除结果
                time.sleep(1)
                self._verify_delete_status(target_torrents)

        except Exception as e:
            logger.error(f"删除种子失败: {e}")

    def _verify_delete_status(self, torrents):
        """验证种子是否真的被删除了"""
        try:
            still_exists = 0
            for torrent in torrents:
                # 尝试获取种子信息
                updated_torrent = self.client.torrents_info(torrent_hashes=torrent.hash)
                if updated_torrent and len(updated_torrent) > 0:
                    still_exists += 1
                    logger.warning(f"种子 {torrent.name} 仍然存在，未成功删除")

            if still_exists == 0:
                logger.info(f"验证结果: 所有 {len(torrents)} 个种子已成功删除")
            else:
                logger.warning(f"验证结果: {still_exists} 个种子未成功删除")
        except Exception as e:
            logger.warning(f"验证删除状态失败: {e}")

    def resume_all(self, exclude_categories: list[str] | None = None):
        """
        恢复暂停的种子，可排除特定分类。

        Args:
            exclude_categories: 要排除的分类列表
        """
        try:
            target_torrents = self._get_torrents_excluding_categories(exclude_categories)

            if target_torrents is None:
                logger.info("没有需要恢复的种子")
                return

            if target_torrents == "all":
                self.client.torrents_resume(torrent_hashes="all")
                logger.info("已发出恢复所有种子的指令")
            else:
                # 逐个恢复以确保成功
                success_count = 0
                for torrent in target_torrents:
                    try:
                        self.client.torrents_resume(torrent_hashes=torrent.hash)
                        success_count += 1
                        logger.debug(f"恢复种子: {torrent.name}")
                    except Exception as e:
                        logger.warning(f"恢复种子 {torrent.name} 失败: {e}")

                logger.info(f"成功恢复 {success_count}/{len(target_torrents)} 个种子")

        except Exception as e:
            logger.error(f"恢复种子失败: {e}")

    def pause_and_delete_all(self, *, delete_files: bool = False, exclude_categories: list[str] | None = None) -> None:
        """
        先强制汇报，再暂停，最后删除任务，可排除特定分类。

        Args:
            delete_files: True 时会连同本地数据一并删除（危险操作）
            exclude_categories: 要排除的分类列表
        """
        logger.info("开始执行：强制汇报 -> 暂停 -> 删除种子")

        # 1. 强制汇报
        self.reannounce_all(exclude_categories=exclude_categories)

        # 2. 暂停种子
        self.pause_all(exclude_categories=exclude_categories)

        # 3. 等待一下确保暂停完成
        time.sleep(2)

        # 4. 删除种子
        self.delete_all(delete_files=delete_files, exclude_categories=exclude_categories)

        logger.info("完成：种子已汇报、暂停并删除")

    def get_torrent_stats_by_category(self) -> dict:
        """
        获取按分类统计的种子信息。

        Returns:
            包含各分类种子数量的字典
        """
        try:
            all_torrents = self.client.torrents.info()
            category_stats = {}

            for torrent in all_torrents:
                category = torrent.category or "未分类"
                if category not in category_stats:
                    category_stats[category] = 0
                category_stats[category] += 1

            return category_stats
        except Exception as e:
            logger.error(f"获取分类统计失败: {e}")
            return {}

    def get_torrent_status(self, exclude_categories: list[str] | None = None) -> dict:
        """
        获取种子状态统计

        Args:
            exclude_categories: 要排除的分类列表

        Returns:
            包含各状态种子数量的字典
        """
        try:
            target_torrents = self._get_torrents_excluding_categories(exclude_categories)

            if target_torrents is None or target_torrents == "all":
                all_torrents = self.client.torrents.info()
            else:
                all_torrents = target_torrents

            status_stats = {}
            for torrent in all_torrents:
                state = torrent.state
                if state not in status_stats:
                    status_stats[state] = 0
                status_stats[state] += 1

            return status_stats
        except Exception as e:
            logger.error(f"获取状态统计失败: {e}")
            return {}
