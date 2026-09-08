---
name: deploy
description: "一键部署 OpenClaw Log ETL + 中心监控服务端到远程 Linux 服务器（SSH + scp + systemd）。"
---

# Deploy

把 OpenClaw Log ETL 的中心监控服务端一键部署到远程 Linux 服务器。

## 前置条件

部署前确认（缺一不可，否则脚本会卡住）：

1. 本机已配好 SSH 免密登录目标机（`ssh root@<服务器>` 能直接进去、不用输密码）
2. 目标机是 Linux 且有 `systemd`（Ubuntu/Debian/CentOS 都行）
3. 目标机已装 `python3` 和 `pip3`

## 快速开始

在仓库根目录执行：

```bash
./deploy.sh root@<服务器地址>
```

脚本自动 scp 上传 → 装依赖 → 初始化数据库 → 写 systemd → 启动服务端。

## 部署后（三步收尾）

```bash
# 1. 注册客户端，拿到 API Key
ssh root@<服务器> 'cd /opt/openclaw-log-etl && python3 -m server.manage register-client server-01 "Linux Server"'

# 2. 把 API Key 填进 reporter 服务
ssh root@<服务器> 'systemctl edit openclaw-reporter'

# 3. 启动上报客户端
ssh root@<服务器> 'systemctl enable --now openclaw-reporter'
```

## 访问

- Dashboard: `http://<服务器>:8000/api/v1/dashboard`
- API 文档: `http://<服务器>:8000/docs`

## 注意

- 默认部署目录是 `/opt/openclaw-log-etl`，服务端口 `8000`
- reporter 服务里的 API Key 默认是 `placeholder`，部署后必须替换，否则上报会被拒
- 中文图表依赖中文字体，脚本不会自动装字体，缺失时手动 `apt install fonts-wqy-zenhei`
