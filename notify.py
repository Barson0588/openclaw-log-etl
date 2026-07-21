"""
通知推送模块 (notify.py)
=========================
ETL 管线完成后通过邮件或企业微信 Webhook 发送日报摘要。

支持的推送通道:
  - SMTP 邮件: 通过 QQ/Gmail/企业邮箱发送 HTML 摘要
  - 企业微信机器人: Webhook 发送 Markdown 消息卡片

配置方式 — 环境变量:
  # SMTP 邮件
  NOTIFY_SMTP_HOST=smtp.qq.com
  NOTIFY_SMTP_PORT=587
  NOTIFY_SMTP_USER=your@qq.com
  NOTIFY_SMTP_PASS=your_auth_code
  NOTIFY_TO=receiver@example.com

  # 企业微信 Webhook
  NOTIFY_WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx

使用方式:
    from notify import Notifier
    notifier = Notifier()
    notifier.send(stats, html_path)
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class Notifier:
    """多渠道通知发送器。

    使用方式::

        notifier = Notifier()
        notifier.send(stats, html_path)  # 根据配置自动选择通道
    """

    def __init__(self):
        self.smtp_host = os.getenv("NOTIFY_SMTP_HOST", "")
        self.smtp_port = int(os.getenv("NOTIFY_SMTP_PORT", "587"))
        self.smtp_user = os.getenv("NOTIFY_SMTP_USER", "")
        self.smtp_pass = os.getenv("NOTIFY_SMTP_PASS", "")
        self.to_email = os.getenv("NOTIFY_TO", "")
        self.wecom_webhook = os.getenv("NOTIFY_WECOM_WEBHOOK", "")

    def send(self, stats, html_path):
        """发送日报通知，根据配置选择可用通道。"""
        sent_any = False
        if self.smtp_host and self.smtp_user and self.to_email:
            try:
                self._send_email(stats, html_path)
                sent_any = True
            except Exception:
                logger.exception("邮件发送失败")
        else:
            logger.debug("SMTP 未配置，跳过邮件通知")

        if self.wecom_webhook:
            try:
                self._send_wecom(stats)
                sent_any = True
            except Exception:
                logger.exception("企业微信通知发送失败")
        else:
            logger.debug("企业微信 Webhook 未配置，跳过通知")

        if not sent_any:
            logger.info("未配置任何通知通道，跳过推送")

    # -----------------------------------------------------------------
    #  SMTP 邮件
    # -----------------------------------------------------------------

    def _send_email(self, stats, html_path):
        """发送 HTML 格式的日报摘要邮件。"""
        subject = (
            f"OpenClaw 监控日报 — "
            f"成功率 {stats['overall_success_rate']}%"
        )

        body_html = self._build_email_body(stats)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.smtp_user
        msg["To"] = self.to_email
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_pass)
            server.send_message(msg)

        logger.info("邮件已发送至 %s", self.to_email)

    def _build_email_body(self, stats):
        """构建简洁的 HTML 邮件正文。"""
        rate = stats["overall_success_rate"]
        if rate >= 95:
            level, color = "良好", "#2a9d8f"
        elif rate >= 85:
            level, color = "需要关注", "#f4a261"
        else:
            level, color = "异常", "#e76f51"

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,'PingFang SC',sans-serif;
             max-width:600px;margin:0 auto;padding:24px;
             color:#2d3436;background:#f5f6fa;">
<div style="background:#fff;border-radius:12px;padding:24px;
            box-shadow:0 1px 3px rgba(0,0,0,.06);">
  <h2 style="margin:0 0 8px 0;">OpenClaw 监控日报</h2>
  <p style="color:#636e72;margin:0 0 20px 0;">
    数据范围: {stats['date_range_start']} ~ {stats['date_range_end']}
  </p>

  <table style="width:100%;border-collapse:collapse;font-size:14px;">
    <tr><td style="padding:6px 0;color:#636e72;">任务总数</td>
        <td style="text-align:right;"><strong>{stats['total_tasks']}</strong></td></tr>
    <tr><td style="padding:6px 0;color:#636e72;">成功率</td>
        <td style="text-align:right;color:{color};font-weight:700;">
          {rate}% ({stats['total_success']}/{stats['total_tasks']})</td></tr>
    <tr><td style="padding:6px 0;color:#636e72;">Token 消耗</td>
        <td style="text-align:right;"><strong>{stats['total_tokens']:,}</strong></td></tr>
    <tr><td style="padding:6px 0;color:#636e72;">平均耗时</td>
        <td style="text-align:right;"><strong>{stats['avg_duration_ms']}</strong> ms</td></tr>
    <tr><td style="padding:6px 0;color:#636e72;">最高频错误</td>
        <td style="text-align:right;">{stats['top_error_type']}</td></tr>
  </table>

  <div style="margin-top:20px;padding:12px 16px;background:#f0f9f4;
              border-radius:8px;font-size:14px;">
    <strong>系统健康评级: {level}</strong>
    <br>预估 API 成本: $
    {stats['total_tokens'] / 1000000 * 4:.2f} (按 $4/1M tokens)
  </div>
</div>
<p style="color:#b0b4b8;font-size:12px;text-align:center;margin-top:16px;">
  报表由 OpenClaw ETL 管线自动生成
</p>
</body>
</html>"""

    # -----------------------------------------------------------------
    #  企业微信机器人 Webhook
    # -----------------------------------------------------------------

    def _send_wecom(self, stats):
        """通过企业微信机器人 Webhook 发送 Markdown 消息卡片。"""
        import json
        import urllib.request

        rate = stats["overall_success_rate"]
        if rate >= 95:
            level = "良好 <font color=\"info\">●</font>"
        elif rate >= 85:
            level = "需要关注 <font color=\"warning\">●</font>"
        else:
            level = "异常 <font color=\"warning\">●</font>"

        cost = stats["total_tokens"] / 1000000 * 4

        content = (
            f"## OpenClaw 监控日报\n"
            f"> 数据范围: {stats['date_range_start']} ~ {stats['date_range_end']}\n"
            f"\n"
            f"- **任务总数**: {stats['total_tasks']}\n"
            f"- **成功率**: {rate}% ({stats['total_success']}/{stats['total_tasks']})\n"
            f"- **Token 消耗**: {stats['total_tokens']:,}\n"
            f"- **预估成本**: ${cost:.2f}\n"
            f"- **平均耗时**: {stats['avg_duration_ms']}ms\n"
            f"- **最高频错误**: {stats['top_error_type']}\n"
            f"- **最高频工具**: {stats['top_tool']}\n"
            f"\n"
            f"系统健康评级: **{level}**"
        )

        payload = json.dumps({
            "msgtype": "markdown",
            "markdown": {"content": content},
        }).encode("utf-8")

        req = urllib.request.Request(
            self.wecom_webhook,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info("企业微信通知已发送 (HTTP %d)", resp.getcode())
