# nezhaV1-exporter

一个用于将 [Nezha 监控平台](https://github.com/naiba/nezha) 的 WebSocket 数据转换为 Prometheus 格式并通过 HTTP 接口暴露的 exporter，方便 Prometheus/Grafana 等监控系统采集和展示。

## 功能简介

- 通过 WebSocket 实时接收 Nezha 监控平台推送的服务器监控数据
- 提供 HTTP 接口，支持获取 Prometheus 格式数据
- 便于与 Prometheus、Grafana 等监控平台集成
- 支持本地运行和 Docker 部署
- **[新功能]** 支持网络延迟监控（Service Monitor），采集各服务器到监控节点的延迟数据

## 架构流程图

```mermaid
flowchart LR
    A[Nezha 监控平台] -- WebSocket 推送 --> B[nezhaV1-exporter]
    A -- Service API --> B
    B -- HTTP 提供数据 --> C[Prometheus]
    C -- 数据展示 --> D[Grafana]
    subgraph Docker
        B
    end
```

### 数据处理流程

```mermaid
flowchart TD
    A[接收 WS 数据] --> B[解析服务器数据]
    B --> B1{"检测 uptime 变化"}
    B1 -- "有变化" --> B2[更新时间戳]
    B1 -- "无变化" --> B3[跳过时间戳更新]
    B2 --> B4[缓存服务器数据]
    B3 --> B4
    G[获取分组信息] --> H[group_map 缓存]
    
    subgraph 服务监控模块
        S1[定时获取在线服务器列表] --> S2[并发请求 Service API]
        S2 --> S3[解析延迟数据]
        S3 --> S4[缓存服务监控数据]
    end
    
    B4 --> S1
    B4 --> C["/metrics 请求"]
    C --> D[过滤过期服务器]
    D --> D1[添加分组信息]
    H -.-> D1
    D1 --> D2{服务监控已启用?}
    D2 -- "是" --> D3[追加服务监控指标]
    S4 -.-> D3
    D2 -- "否" --> E["返回数据<br/>(含分组信息)"]
    D3 --> E
```

### 数据过期机制

- 通过检测 `uptime` 是否变化来判断服务器是否真正在线
- 服务器离线后，`uptime` 停止变化，超过 60 秒后该服务器的指标自动从输出中移除
- 服务器重新上线后，指标自动恢复

### 多分组支持

- 支持主机同时属于多个分组
- Prometheus 指标会为每个分组单独输出一条记录

> 详细的数据处理流程请参阅 [nezha-exporter.md](nezha-exporter.md)

## 依赖要求

- Python 3.10+
- 依赖库：`websockets`、`aiohttp`

## 快速开始

### 1. 本地运行

1. 安装依赖

   ```bash
   pip install websockets aiohttp
   ```

2. 设置环境变量：

   ```bash
   # Windows（基础配置）
   set WS_URL=wss://nezha.example.com/api/v1/ws/server
   set GROUP_URL=https://nezha.example.com/api/v1/server-group

   # Windows（启用服务监控，可选）
   set SERVICE_MONITOR_ENABLED=true
   set SERVICE_URL=https://nezha.example.com/api/v1/service

   # Linux/Mac（基础配置）
   export WS_URL=wss://nezha.example.com/api/v1/ws/server
   export GROUP_URL=https://nezha.example.com/api/v1/server-group

   # Linux/Mac（启用服务监控，可选）
   export SERVICE_MONITOR_ENABLED=true
   export SERVICE_URL=https://nezha.example.com/api/v1/service
   ```

3. 启动程序

   ```bash
   python nezha-exporter.py
   ```

4. 默认 HTTP 服务监听 8080 端口，可通过以下接口获取数据：

   - `http://localhost:8080/metrics` 获取 Prometheus 格式数据
   - `http://localhost:8080/latest_message.prom` 获取 Prometheus 格式数据（兼容旧版）

### 2. Docker 部署

1. 构建镜像

   ```bash
   docker build -t nezha-exporter .
   ```

2. 运行容器（需设置环境变量 WS_URL 和 GROUP_URL）

   ```bash
   docker run -d --name nezha-exporter \
     -e WS_URL=wss://nezha.example.com/api/v1/ws/server \
     -e GROUP_URL=https://nezha.example.com/api/v1/server-group \
     -p 8009:8080 nezha-exporter
   ```

   - 其中 `-p 8009:8080` 表示将主机 8009 端口映射到容器 8080 端口

### 3. Docker Compose 部署

1. 编辑 `docker-compose.yml`，设置正确的 `WS_URL` 和 `GROUP_URL`

2. 启动服务

   ```bash
   docker-compose up -d
   ```

## HTTP API

| 端点路径 | 响应类型 | 说明 |
|---------|---------|------|
| `/metrics` | text/plain | 返回 Prometheus 格式的指标数据（已过滤过期服务器，包含分组标签） |
| `/latest_message.prom` | text/plain | 同 `/metrics`，兼容旧版 |

## 配置说明

| 环境变量 | 必填 | 说明 |
|---------|------|------|
| `WS_URL` | 是 | 哪吒监控 WebSocket 地址，例如 `wss://nezha.example.com/api/v1/ws/server` |
| `GROUP_URL` | 是 | 分组信息 API 地址，例如 `https://nezha.example.com/api/v1/server-group` |
| `SERVICE_MONITOR_ENABLED` | 否 | 是否启用服务监控功能，可选值：`true`/`false`（默认 `false`） |
| `SERVICE_URL` | 否* | 服务监控 API 地址，例如 `https://nezha.example.com/api/v1/service`<br/>*当 `SERVICE_MONITOR_ENABLED=true` 时必填 |
| `AUTH_USERNAME` | 否 | Basic Auth 用户名（与 `AUTH_PASSWORD` 同时设置时生效） |
| `AUTH_PASSWORD` | 否 | Basic Auth 密码（与 `AUTH_USERNAME` 同时设置时生效） |

### 服务监控功能（Service Monitor）

服务监控功能可以采集各服务器到监控节点的网络延迟数据。启用后，会定期从 Service API 获取所有在线服务器的延迟监控数据，并以 Prometheus 格式暴露。

**Prometheus 指标格式：**

```prometheus
# HELP nezha_service_avg_delay_ms Average network delay in milliseconds
# TYPE nezha_service_avg_delay_ms gauge
nezha_service_avg_delay_ms{id="12",name="MoeGZ",group="默认",monitor_id="2",monitor_name="AWS_SG_ipv6"} 97.018 1765626600000
```

> 注：时间戳（毫秒级整数）放在数值后面。每个监控节点输出最新 3 个数据点。标签名与基础指标保持一致（id, name, group）。

**标签说明：**

| 标签 | 说明 |
|------|------|
| `id` | 服务器 ID |
| `name` | 服务器名称 |
| `group` | 服务器分组（支持多分组，每个分组输出一条指标） |
| `monitor_id` | 监控节点 ID |
| `monitor_name` | 监控节点名称 |

**启用服务监控示例：**

```bash
docker run -d --name nezha-exporter \
  -e WS_URL=wss://nezha.example.com/api/v1/ws/server \
  -e GROUP_URL=https://nezha.example.com/api/v1/server-group \
  -e SERVICE_MONITOR_ENABLED=true \
  -e SERVICE_URL=https://nezha.example.com/api/v1/service \
  -p 8009:8080 nezha-exporter
```

### Basic Auth 认证

如果你的 Nezha 监控平台启用了 HTTP Basic Auth 认证，可以通过设置 `AUTH_USERNAME` 和 `AUTH_PASSWORD` 环境变量来传入认证信息。

**Docker 运行示例：**

```bash
docker run -d --name nezha-exporter \
  -e WS_URL=wss://nezha.example.com/api/v1/ws/server \
  -e GROUP_URL=https://nezha.example.com/api/v1/server-group \
  -e AUTH_USERNAME=your_username \
  -e AUTH_PASSWORD=your_password \
  -p 8009:8080 nezha-exporter
```

**Docker Compose 示例：**

```yaml
services:
  nezha-exporter:
    build: .
    environment:
      WS_URL: wss://nezha.example.com/api/v1/ws/server
      GROUP_URL: https://nezha.example.com/api/v1/server-group
      AUTH_USERNAME: your_username
      AUTH_PASSWORD: your_password
    ports:
      - "8009:8080"
```

**Docker Compose 完整示例（含服务监控）：**

```yaml
services:
  nezha-exporter:
    build: .
    environment:
      WS_URL: wss://nezha.example.com/api/v1/ws/server
      GROUP_URL: https://nezha.example.com/api/v1/server-group
      SERVICE_MONITOR_ENABLED: "true"
      SERVICE_URL: https://nezha.example.com/api/v1/service
      AUTH_USERNAME: your_username  # 可选
      AUTH_PASSWORD: your_password  # 可选
    ports:
      - "8009:8080"
```

> 注意：只有当 `AUTH_USERNAME` 和 `AUTH_PASSWORD` 都设置时，才会启用 Basic Auth 认证。如果只设置其中一个或都不设置，则不使用认证。

## 监控平台集成

- 推荐将 `/metrics` 接口作为 Prometheus 的 scrape target，采集 Nezha 监控数据并在 Grafana 等平台展示。

- Grafana 演示地址：[Nezha 监控数据 Dashboard 示例](https://grafana2.moeyuuko.com/d/edsum8gy9f08we/nezha)

## 贡献方式

欢迎提交 issue 或 PR 改进本项目。
