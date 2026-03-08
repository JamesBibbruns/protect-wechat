#!/usr/bin/env python3
import os
import sys
import json
import logging
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fetch_page_content(url: str, timeout: int = 30000) -> str:
    """使用 Playwright 抓取页面内容"""
    with sync_playwright() as p:
        # 优化5: 使用更轻量的浏览器配置
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--window-size=1920,1080',
            ]
        )
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.0'
        )
        
        page = context.new_page()
        
        try:
            logger.info(f"正在访问: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            
            # 优化6: 等待特定元素而非固定时间
            page.wait_for_selector('div.stats-box', timeout=10000)
            # 额外等待网络稳定
            page.wait_for_load_state('networkidle', timeout=10000)
            
            html = page.content()
            logger.info("页面抓取成功")
            return html
            
        except PlaywrightTimeout:
            logger.error("页面加载超时")
            # 超时后仍尝试获取内容
            return page.content()
        except Exception as e:
            logger.error(f"页面访问失败: {e}")
            raise
        finally:
            context.close()
            browser.close()

def parse_stats(html: str) -> tuple[str, str]:
    """解析用餐统计数据"""
    soup = BeautifulSoup(html, "lxml")
    
    # 优化7: 更健壮的选择器，支持多种可能结构
    selectors = [
        'div.stats-box',
        '[class*="stats"]',
        '[class*="stat"]',
        '.lunch-stats',
        '#stats'
    ]
    
    box = None
    for selector in selectors:
        box = soup.select_one(selector)
        if box:
            logger.info(f"使用选择器找到元素: {selector}")
            break
    
    if not box:
        logger.warning("未找到统计元素，保存页面内容用于调试")
        with open('debug_page.html', 'w', encoding='utf-8') as f:
            f.write(html)
        raise ValueError("页面中找不到统计元素")
    
    # 优化8: 更灵活的文本提取
    num_elem = box.find('div') or box.find('span') or box.find('p')
    title_elem = box.find('h3') or box.find('h2') or box.find('h1') or box.find('strong')
    
    if not num_elem or not title_elem:
        raise ValueError("统计元素内缺少数值或标题")
    
    return title_elem.get_text(strip=True), num_elem.get_text(strip=True)

def send_wecom_notification(key: str, title: str, num: str) -> None:
    """推送到企业微信"""
    if not key:
        raise ValueError("企业微信 Webhook Key 未配置")
    
    # 优化9: 修复 URL 拼接空格问题
    webhook = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key.strip()}"
    
    # 优化10: 更美观的消息格式
    md = f"""## 🍽️ 今日用餐统计

> **{title}**
> 
> 👥 **{num}** 人

⏰ 更新时间：北京时间 08:00"""
    
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": md}
    }
    
    try:
        resp = requests.post(
            webhook, 
            json=payload, 
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )
        resp.raise_for_status()
        result = resp.json()
        
        if result.get('errcode') == 0:
            logger.info("✅ 推送成功")
        else:
            logger.error(f"推送失败: {result}")
            raise RuntimeError(f"企业微信API错误: {result}")
            
    except requests.exceptions.Timeout:
        logger.error("推送请求超时")
        raise
    except Exception as e:
        logger.error(f"推送失败: {e}")
        raise

def main():
    try:
        key = os.getenv('WECOM_WEBHOOK_KEY', '').strip()
        url = os.getenv('LUNCH_URL', '').strip()
        
        if not key or not url:
            raise ValueError("缺少必要的环境变量: WECOM_WEBHOOK_KEY 或 LUNCH_URL")
        
        # 抓取
        html = fetch_page_content(url)
        
        # 解析
        title, num = parse_stats(html)
        logger.info(f"解析结果: {title} - {num}人")
        
        # 推送
        send_wecom_notification(key, title, num)
        
    except Exception as e:
        logger.error(f"❌ 任务失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
