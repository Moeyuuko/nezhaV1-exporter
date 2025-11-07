# nezhaV1-exporter

一个用于将 [Nezha 监控平台](https://github.com/naiba/nezha) 的 WebSocket 数据转换为 Prometheus 格式并通过 HTTP 接口暴露的 exporter，方便 Prometheus/Grafana 等监控系统采集和展示。

## 功能简介

- 通过 WebSocket 实时接收 Nezha 监控平台推送的服务器监控数据
- 提供 HTTP 接口，支持获取最新的 JSON 数据和 Prometheus 格式数据
- 便于与 Prometheus、Grafana 等监控平台集成
- 支持本地运行和 Docker 部署

## 依赖要求

- Python 3.10+
- 依赖库：`websockets`、`aiohttp`

## 快速开始

### 1. 本地运行

1. 安装依赖

   ```bash
   pip install websockets aiohttp
   ```

2. 设置环境变量 `WS_URL`，指向 Nezha 监控平台的 WebSocket 地址。例如：

   ```bash
   set WS_URL=wss://nezha.example.com/api/v1/ws/server
   ```

3. 启动程序

   ```bash
   python nezha-exporter.py
   ```

4. 默认 HTTP 服务监听 8080 端口，可通过以下接口获取数据：

   - `http://localhost:8080/latest_message.json` 获取最新 JSON 数据
   - `http://localhost:8080/latest_message.prom` 获取 Prometheus 格式数据

### 2. Docker 部署

1. 构建镜像

   ```bash
   docker build -t nezha-exporter .
   ```

2. 运行容器（需设置环境变量 WS_URL）

   ```bash
   docker run -d --name nezha-exporter -e WS_URL=wss://nezha.example.com/api/v1/ws/server -p 8009:8080 nezha-exporter
   ```

   - 其中 `-p 8009:8080` 表示将主机 8009 端口映射到容器 8080 端口

### 3. Docker Compose 部署

1. 编辑 `docker-compose.yml`，设置正确的 WS_URL

2. 启动服务

   ```bash
   docker-compose up -d
   ```

## HTTP API

- `/latest_message.json`  
  返回最新的原始 JSON 数据

- `/latest_message.prom`  
  返回最新的 Prometheus 格式监控数据

## 配置说明

- `WS_URL` 环境变量必须设置为 Nezha 监控平台的 WebSocket 地址，否则程序无法正常启动。

## 监控平台集成

- 推荐将 `/latest_message.prom` 接口作为 Prometheus 的 scrape target，采集 Nezha 监控数据并在 Grafana 等平台展示。

- Grafana 演示地址：[Nezha 监控数据 Dashboard 示例](https://grafana2.moeyuuko.com/d/edsum8gy9f08we/nezha)

## 贡献方式

欢迎提交 issue 或 PR 改进本项目。
