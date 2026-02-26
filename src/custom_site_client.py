import os
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from logger import LOG


@dataclass
class SiteConfig:
    name: str
    url: str
    item_selector: str
    title_selector: str
    link_selector: str = "a"
    summary_selector: str | None = None
    base_url: str | None = None


class CustomSiteClient:
    """
    通用站点抓取客户端。
    通过站点配置（CSS Selector）抓取任意门户网站并导出为 Markdown。
    """

    def __init__(self):
        self.timeout = 15
        self.session = requests.Session()
        # 避免读取系统代理导致的抓取异常（可按需调整）
        self.session.trust_env = False
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        self.site_configs: dict[str, SiteConfig] = {}
        self._register_builtin_sites()

    def _register_builtin_sites(self):
        # 默认提供两个 OpenAI 博客源（RSS），稳定性高于动态网页。
        self.register_site(
            SiteConfig(
                name="openai_blog",
                url="https://openai.com/news/rss.xml",
                item_selector="item",
                title_selector="title",
                link_selector="link",
                summary_selector="description",
                base_url="https://openai.com",
            )
        )
        self.register_site(
            SiteConfig(
                name="openai_research",
                url="https://openai.com/research/rss.xml",
                item_selector="item",
                title_selector="title",
                link_selector="link",
                summary_selector="description",
                base_url="https://openai.com",
            )
        )

    def register_site(self, config: SiteConfig):
        self.site_configs[config.name] = config
        LOG.info("已注册自定义站点: {}", config.name)

    def list_sites(self) -> list[str]:
        return list(self.site_configs.keys())

    def has_site(self, site_name: str) -> bool:
        return site_name in self.site_configs

    def fetch_site_items(self, site_name: str, limit: int = 30) -> list[dict[str, str]]:
        LOG.debug("准备抓取站点: {}", site_name)
        config = self.site_configs.get(site_name)
        if not config:
            raise ValueError(f"未找到站点配置: {site_name}")

        try:
            response = self.session.get(config.url, timeout=self.timeout, headers=self.headers)
            response.raise_for_status()
            items = self._parse_items(response.text, config)
            LOG.info("站点 {} 解析成功，共 {} 条", site_name, len(items))
            return items[:limit]
        except Exception as exc:
            LOG.error("抓取站点 {} 失败：{}", site_name, str(exc))
            return []

    def _parse_items(self, html: str, config: SiteConfig) -> list[dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        item_nodes = soup.select(config.item_selector)
        parsed_items: list[dict[str, str]] = []

        for node in item_nodes:
            title_node = node.select_one(config.title_selector)
            if not title_node:
                continue

            link_node = node.select_one(config.link_selector) if config.link_selector else title_node
            raw_link = ""
            if link_node:
                raw_link = (link_node.get("href", "") or "").strip()
                # 兼容 RSS 中 <link>https://...</link> 这类纯文本链接
                if not raw_link:
                    raw_link = link_node.get_text(strip=True)
            full_link = urljoin(config.base_url or config.url, raw_link) if raw_link else ""
            title = title_node.get_text(strip=True)

            summary = ""
            if config.summary_selector:
                summary_node = node.select_one(config.summary_selector)
                if summary_node:
                    summary = summary_node.get_text(strip=True)

            if title:
                parsed_items.append(
                    {
                        "title": title,
                        "link": full_link,
                        "summary": summary,
                    }
                )

        return parsed_items

    def export_site_items(self, site_name: str, date: str | None = None, hour: str | None = None):
        LOG.debug("准备导出站点信息: {}", site_name)
        try:
            items = self.fetch_site_items(site_name)
        except ValueError as exc:
            LOG.error("站点配置错误：{}", str(exc))
            return None
        if not items:
            LOG.warning("站点 {} 没有可导出的内容。", site_name)
            return None

        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        if hour is None:
            hour = datetime.now().strftime("%H")

        dir_path = os.path.join("custom_sites", site_name, date)
        os.makedirs(dir_path, exist_ok=True)

        file_path = os.path.join(dir_path, f"{hour}.md")
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(f"# {site_name} 热门信息 ({date} {hour}:00)\n\n")
            for idx, item in enumerate(items, start=1):
                file.write(f"{idx}. [{item['title']}]({item['link']})\n")
                if item["summary"]:
                    file.write(f"   - 摘要：{item['summary']}\n")

        LOG.info("站点 {} 信息导出完成: {}", site_name, file_path)
        return file_path


if __name__ == "__main__":
    client = CustomSiteClient()
    client.export_site_items("zhihu")
