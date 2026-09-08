---
name: deploy
description: "一键部署 OpenClaw Log ETL + 中心监控服务端到远程 Linux 服务器（SSH + scp + systemd）。"
---

# Deploy

把 OpenClaw Log ETL + 中心监控服务端一键部署到远程 Linux 服务器。

## 使用方式

在仓库根目录执行：

```bash
bash skills/deploy/scripts/deploy.sh root@<服务器地址>
```

脚本会依次完成：

1. scp 上传核心 ETL 模块、服务端、客户端、模板文件
2. 在服务器上安装依赖、初始化数据库
3. 写入 systemd 服务（`openclaw-server` + `openclaw-reporter`）
4. 启动服务端并尝试开放防火墙端口

## 部署后

```bash
# 在服务器上注册客户端，拿到 API Key
ssh root@<服务器> 'cd /opt/openclaw-log-etl && python3 -m server.manage register-client server-01 "Linux Server"'

# 把 API Key 填进 reporter 服务
ssh root@<服务器> 'systemctl edit openclaw-reporter'

# 启动上报客户端
ssh root@<服务器> 'systemctl enable --now openclaw-reporter'
```

## 访问

- Dashboard: `http://<服务器>:8000/api/v1/dashboard`
- API 文档: `http://<服务器>:8000/docs`

## 注意

- 目标机器需已配置 SSH 免密登录（脚本用 scp + ssh，不交互输密码）
- 默认部署目录是 `/opt/openclaw-log-etl`，服务端口 `8000`
- reporter 服务里的 API Key 默认是 `placeholder`，部署后必须替换，否则上报会被拒
- 中文图表依赖中文字体，脚本不会自动装字体，缺失时手动 `apt install fonts-wqy-zenhei`
