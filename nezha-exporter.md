# nezha-exporter 数据处理详细流程

本流程图展示了 NezhaV1-exporter 对 WebSocket 数据的接收、解析、转换及对外接口输出的详细内部流程。

## 整体架构

```mermaid
flowchart TD
    subgraph 数据源
        WS["WebSocket 连接<br/>WS_URL"]
        API["HTTP API<br/>GROUP_URL"]
    end
    
    subgraph 核心处理
        WS --> LISTEN["listen() 监听循环"]
        API --> FETCH["fetch_groups() 分组获取<br/>每60秒刷新"]
        LISTEN --> PARSE["JSON 解析"]
        PARSE --> CONVERT["convert_to_prometheus_text()<br/>数据转换"]
        FETCH --> GMAP["group_map 缓存<br/>服务器ID → 分组名"]
    end
    
    subgraph 数据缓存
        CONVERT --> JSON_CACHE["latest_json_data<br/>JSON 格式缓存"]
        CONVERT --> PROM_CACHE["latest_prom_data<br/>Prometheus 格式缓存"]
        GMAP -.-> CONVERT
    end
    
    subgraph HTTP服务 ["HTTP 服务 (端口 8080)"]
        JSON_CACHE --> EP1["/latest_message.json"]
        PROM_CACHE --> EP2["/latest_message.prom"]
        PROM_CACHE --> EP3["/metrics"]
    end
```

## 详细数据流程

```mermaid
flowchart TD
    A["WS 连接建立"] --> B["接收 WebSocket 消息"]
    B --> C{"JSON 解析"}
    C -- "解析成功" --> D["提取 online 字段"]
    C -- "解析失败" --> E["记录非JSON消息"]
    
    D --> F["遍历 servers 数组"]
    
    subgraph 服务器数据提取 ["服务器数据提取"]
        F --> G["提取基础信息<br/>id, name"]
        G --> H["从 group_map 获取分组名"]
        H --> I["提取 host 字段"]
        H --> J["提取 state 字段"]
        
        I --> I1["boot_time - 启动时间"]
        I --> I2["mem_total - 总内存"]
        I --> I3["disk_total - 总磁盘"]
        I --> I4["swap_total - 总交换分区"]
        
        J --> J1["cpu - CPU使用率"]
        J --> J2["mem_used - 已用内存"]
        J --> J3["swap_used - 已用交换分区"]
        J --> J4["disk_used - 已用磁盘"]
        J --> J5["net_in_speed - 入站网速"]
        J --> J6["net_out_speed - 出站网速"]
        J --> J7["net_in_transfer - 入站流量"]
        J --> J8["net_out_transfer - 出站流量"]
        J --> J9["tcp_conn_count - TCP连接数"]
        J --> J10["udp_conn_count - UDP连接数"]
        J --> J11["process_count - 进程数"]
        J --> J12["uptime - 运行时间"]
        J --> J13["temperatures - 温度信息数组"]
    end
    
    I1 & I2 & I3 & I4 & J1 & J2 & J3 & J4 & J5 & J6 & J7 & J8 & J9 & J10 & J11 & J12 & J13 --> K["生成 Prometheus 格式文本"]
    K --> L["更新缓存数据"]
    
    L --> M{"外部 API 请求"}
    M -- "/latest_message.json" --> N["返回 JSON 格式数据"]
    M -- "/latest_message.prom" --> O["返回 Prometheus 格式数据"]
    M -- "/metrics" --> O
    M -- "其它路径" --> P["返回 404"]
```

## 分组信息获取流程

```mermaid
flowchart TD
    A["启动 fetch_groups 协程"] --> B["HTTP GET 请求 GROUP_URL"]
    B --> C{"响应状态"}
    C -- "200 OK" --> D["解析 JSON 响应"]
    C -- "其它状态" --> E["记录错误日志"]
    
    D --> F{"success 字段"}
    F -- "true" --> G["遍历 data 数组"]
    F -- "false" --> E
    
    G --> H["提取 group.name"]
    H --> I["遍历 servers 数组"]
    I --> J["建立 server_id → group_name 映射"]
    J --> K["更新 group_map"]
    
    K --> L["等待 60 秒"]
    E --> L
    L --> B
```

## Prometheus 指标说明

| 指标名称 | 类型 | 标签 | 说明 |
|---------|------|------|------|
| `nezha_online` | Gauge | 无 | 在线服务器数量 |
| `nezha_boot_time` | Gauge | id, name, group | 系统启动时间戳 |
| `nezha_mem_total` | Gauge | id, name, group | 总内存（字节） |
| `nezha_disk_total` | Gauge | id, name, group | 总磁盘空间（字节） |
| `nezha_swap_total` | Gauge | id, name, group | 总交换分区（字节） |
| `nezha_cpu` | Gauge | id, name, group | CPU 使用率（百分比） |
| `nezha_mem_used` | Gauge | id, name, group | 已用内存（字节） |
| `nezha_swap_used` | Gauge | id, name, group | 已用交换分区（字节） |
| `nezha_disk_used` | Gauge | id, name, group | 已用磁盘空间（字节） |
| `nezha_net_in_speed` | Gauge | id, name, group | 入站网络速度（字节/秒） |
| `nezha_net_out_speed` | Gauge | id, name, group | 出站网络速度（字节/秒） |
| `nezha_net_in_transfer` | Counter | id, name, group | 入站总流量（字节） |
| `nezha_net_out_transfer` | Counter | id, name, group | 出站总流量（字节） |
| `nezha_tcp_conn_count` | Gauge | id, name, group | TCP 连接数 |
| `nezha_udp_conn_count` | Gauge | id, name, group | UDP 连接数 |
| `nezha_process_count` | Gauge | id, name, group | 进程数 |
| `nezha_uptime` | Gauge | id, name, group | 运行时间（秒） |
| `nezha_temperature` | Gauge | id, name, group, temp_name | 温度传感器读数（摄氏度） |

## 环境变量配置

| 变量名 | 必填 | 说明 |
|-------|------|------|
| `WS_URL` | 是 | 哪吒监控 WebSocket 地址 |
| `GROUP_URL` | 是 | 分组信息 API 地址 |

## HTTP 端点

| 端点路径 | 响应类型 | 说明 |
|---------|---------|------|
| `/latest_message.json` | application/json | 返回最新的原始 JSON 数据 |
| `/latest_message.prom` | text/plain | 返回 Prometheus 格式的指标数据 |
| `/metrics` | text/plain | 同 `/latest_message.prom`，用于 Prometheus 抓取 |

## 错误处理

- WebSocket 连接断开或失败时，自动每 5 秒重连
- 分组信息获取失败时，记录日志并在下一个周期重试
- 数据未就绪时，HTTP 端点返回 503 状态码和 "No data yet" 消息


## 文档流程图注意规格：
> **⚠️ Mermaid 语法注意事项**
> 
> 编写 Mermaid 流程图时，如果节点标签包含以下特殊字符，必须用双引号 `""` 括起来：
> - 问号 `?`
> - 比较符号 `>` `<` `>=` `<=`
> - 乘号 `×` （建议用字母 `x` 替代）
> - 百分号 `%`
> 
> **正确示例**：`A{"是否继续?"}` `B{"值 > 100"}`
> 
> **错误示例**：`A{是否继续?}` `B{值>100}`