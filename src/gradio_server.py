import gradio as gr  # 导入gradio库用于创建GUI
from urllib.parse import urlparse

from config import Config  # 导入配置管理模块
from github_client import GitHubClient  # 导入用于GitHub API操作的客户端
from hacker_news_client import HackerNewsClient
from custom_site_client import CustomSiteClient, SiteConfig
from report_generator import ReportGenerator  # 导入报告生成器模块
from llm import LLM  # 导入可能用于处理语言模型的LLM类
from subscription_manager import SubscriptionManager  # 导入订阅管理器

# 创建各个组件的实例
config = Config()
github_client = GitHubClient(config.github_token)
hacker_news_client = HackerNewsClient() # 创建 Hacker News 客户端实例
custom_site_client = CustomSiteClient()  # 创建自定义站点客户端实例
subscription_manager = SubscriptionManager(config.subscriptions_file)


def _build_report_generator(model_type, model_name):
    config.llm_model_type = model_type
    if model_type == "openai":
        config.openai_model_name = model_name
    else:
        config.ollama_model_name = model_name
    llm = LLM(config)
    return ReportGenerator(llm, config.report_types)


def _normalize_site_name(raw_name, fallback_url):
    name = (raw_name or "").strip().lower()
    if not name:
        host = urlparse(fallback_url).netloc
        name = host.replace(".", "_")
    return name.replace(" ", "_")

def generate_github_report(model_type, model_name, repo, days):
    report_generator = _build_report_generator(model_type, model_name)

    # 定义一个函数，用于导出和生成指定时间范围内项目的进展报告
    raw_file_path = github_client.export_progress_by_date_range(repo, days)  # 导出原始数据文件路径
    report, report_file_path = report_generator.generate_github_report(raw_file_path)  # 生成并获取报告内容及文件路径

    return report, report_file_path  # 返回报告内容和报告文件路径

def generate_hn_hour_topic(model_type, model_name):
    report_generator = _build_report_generator(model_type, model_name)

    markdown_file_path = hacker_news_client.export_top_stories()
    report, report_file_path = report_generator.generate_hn_topic_report(markdown_file_path)

    return report, report_file_path  # 返回报告内容和报告文件路径


def generate_custom_site_report(
    model_type,
    model_name,
    site_name,
    custom_site_name,
    custom_site_url,
    custom_item_selector,
    custom_title_selector,
    custom_link_selector,
    custom_summary_selector,
    custom_base_url,
):
    report_generator = _build_report_generator(model_type, model_name)
    chosen_site = site_name

    # 若填写了临时站点规则，则优先使用临时站点配置
    if custom_site_url and custom_item_selector and custom_title_selector:
        parsed_url = urlparse(custom_site_url.strip())
        if not parsed_url.scheme or not parsed_url.netloc:
            return "临时站点 URL 无效，请输入完整地址（如 https://example.com）。", None

        chosen_site = _normalize_site_name(custom_site_name, custom_site_url)
        resolved_base_url = (custom_base_url or "").strip() or f"{parsed_url.scheme}://{parsed_url.netloc}"
        custom_site_client.register_site(
            SiteConfig(
                name=chosen_site,
                url=custom_site_url.strip(),
                item_selector=custom_item_selector.strip(),
                title_selector=custom_title_selector.strip(),
                link_selector=(custom_link_selector or "a").strip(),
                summary_selector=(custom_summary_selector or "").strip() or None,
                base_url=resolved_base_url,
            )
        )
    elif not chosen_site:
        return "请选择内置站点，或填写临时站点 URL 与选择器。", None

    markdown_file_path = custom_site_client.export_site_items(chosen_site)
    if not markdown_file_path:
        return "未抓取到可用数据，请检查站点规则或稍后重试。", None

    report, report_file_path = report_generator.generate_custom_site_report(markdown_file_path, chosen_site)
    return report, report_file_path


# 定义一个回调函数，用于根据 Radio 组件的选择返回不同的 Dropdown 选项
def update_model_list(model_type):
    if model_type == "openai":
        return gr.Dropdown(choices=["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"], label="选择模型")
    elif model_type == "ollama":
        return gr.Dropdown(choices=["llama3.1", "gemma2:2b", "qwen2:7b"], label="选择模型")


# 创建 Gradio 界面
with gr.Blocks(title="GitHubSentinel") as demo:
    # 创建 GitHub 项目进展 Tab
    with gr.Tab("GitHub 项目进展"):
        gr.Markdown("## GitHub 项目进展")  # 添加小标题

        # 创建 Radio 组件
        model_type = gr.Radio(["openai", "ollama"], label="模型类型", info="使用 OpenAI GPT API 或 Ollama 私有化模型服务")

        # 创建 Dropdown 组件
        model_name = gr.Dropdown(choices=["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"], label="选择模型")

        # 创建订阅列表的 Dropdown 组件
        subscription_list = gr.Dropdown(subscription_manager.list_subscriptions(), label="订阅列表", info="已订阅GitHub项目")

        # 创建 Slider 组件
        days = gr.Slider(value=2, minimum=1, maximum=7, step=1, label="报告周期", info="生成项目过去一段时间进展，单位：天")

        # 使用 radio 组件的值来更新 dropdown 组件的选项
        model_type.change(fn=update_model_list, inputs=model_type, outputs=model_name)

        # 创建按钮来生成报告
        button = gr.Button("生成报告")

        # 设置输出组件
        markdown_output = gr.Markdown()
        file_output = gr.File(label="下载报告")

        # 将按钮点击事件与导出函数绑定
        button.click(generate_github_report, inputs=[model_type, model_name, subscription_list, days], outputs=[markdown_output, file_output])

    # 创建 Hacker News 热点话题 Tab
    with gr.Tab("Hacker News 热点话题"):
        gr.Markdown("## Hacker News 热点话题")  # 添加小标题

        # 创建 Radio 组件
        model_type = gr.Radio(["openai", "ollama"], label="模型类型", info="使用 OpenAI GPT API 或 Ollama 私有化模型服务")

        # 创建 Dropdown 组件
        model_name = gr.Dropdown(choices=["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"], label="选择模型")

        # 使用 radio 组件的值来更新 dropdown 组件的选项
        model_type.change(fn=update_model_list, inputs=model_type, outputs=model_name)

        # 创建按钮来生成报告
        button = gr.Button("生成最新热点话题")

        # 设置输出组件
        markdown_output = gr.Markdown()
        file_output = gr.File(label="下载报告")

        # 将按钮点击事件与导出函数绑定
        button.click(generate_hn_hour_topic, inputs=[model_type, model_name,], outputs=[markdown_output, file_output])

    # 创建自定义站点热点整理 Tab
    with gr.Tab("自定义网站信息整理"):
        gr.Markdown("## 自定义网站信息整理")

        model_type = gr.Radio(["openai", "ollama"], label="模型类型", info="使用 OpenAI GPT API 或 Ollama 私有化模型服务")
        model_name = gr.Dropdown(choices=["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"], label="选择模型")
        site_name = gr.Dropdown(choices=custom_site_client.list_sites(), label="站点列表", info="已内置站点，可在代码中继续注册")

        model_type.change(fn=update_model_list, inputs=model_type, outputs=model_name)

        with gr.Accordion("临时站点规则（可选）", open=False):
            gr.Markdown("填写后将覆盖“站点列表”，按你输入的规则临时抓取任意网站。")
            custom_site_name = gr.Textbox(label="临时站点名称（可选）", placeholder="例如: my_blog")
            custom_site_url = gr.Textbox(label="临时站点 URL", placeholder="https://example.com")
            custom_item_selector = gr.Textbox(label="列表项选择器 item_selector", placeholder=".news-item")
            custom_title_selector = gr.Textbox(label="标题选择器 title_selector", placeholder=".title")
            custom_link_selector = gr.Textbox(label="链接选择器 link_selector（默认 a）", placeholder="a")
            custom_summary_selector = gr.Textbox(label="摘要选择器 summary_selector（可选）", placeholder=".summary")
            custom_base_url = gr.Textbox(label="base_url（可选）", placeholder="https://example.com")

        button = gr.Button("生成站点报告")
        markdown_output = gr.Markdown()
        file_output = gr.File(label="下载报告")

        button.click(
            generate_custom_site_report,
            inputs=[
                model_type,
                model_name,
                site_name,
                custom_site_name,
                custom_site_url,
                custom_item_selector,
                custom_title_selector,
                custom_link_selector,
                custom_summary_selector,
                custom_base_url,
            ],
            outputs=[markdown_output, file_output],
        )



if __name__ == "__main__":
    demo.launch(share=True, server_name="0.0.0.0")  # 启动界面并设置为公共可访问
    # 可选带有用户认证的启动方式
    # demo.launch(share=True, server_name="0.0.0.0", auth=("django", "1234"))