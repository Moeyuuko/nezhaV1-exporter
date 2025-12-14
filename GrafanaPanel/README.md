# Nezha Grafana Dashboard

这是 nezha-exporter 的 Grafana 仪表板配置文件。

## 仪表板文件说明

| 文件名 | 说明 | 使用场景 |
|--------|------|----------|
| `Nezha-grafana.json` | 主仪表板 | 综合监控，包含服务器状态和服务延迟监控 |
| `Nezha_service.json` | 服务监控专用仪表板 | 专注于网络延迟监控，按分组和监控节点展示 |

## 导入说明

### 主仪表板 (Nezha-grafana.json)

1. 在 Grafana 中，进入 **Dashboards** → **Import**
2. 上传 `Nezha-grafana.json` 文件或粘贴其内容
3. 选择对应的 Prometheus 数据源

### 服务监控仪表板 (Nezha_service.json)

1. 在 Grafana 中，进入 **Dashboards** → **Import**
2. 上传 `Nezha_service.json` 文件或粘贴其内容
3. 在导入页面配置以下选项：
   - **Prometheus**: 选择您的 Prometheus 数据源
   - **作业 (VAR_JOB)**: 输入您的 Prometheus job 名称（默认 `nezhav1`）

> **注意**: `Nezha_service.json` 需要启用 nezha-exporter 的服务监控功能（`SERVICE_MONITOR_ENABLED=true`）才能获取到数据。

## ⚠️ 重要配置

### 配置 job 变量

导入仪表板后，**必须将 `job` 变量设置为您在 Prometheus 配置中定义的 job 名称**。

默认值为 `nezhav1`，如果您的 Prometheus scrape 配置中使用了不同的 job 名称，需要进行修改：

1. 进入仪表板设置（点击右上角齿轮图标）
2. 选择 **Variables**
3. 编辑 `job` 变量
4. 将值修改为您的 Prometheus 配置中对应的 job 名称

例如，如果您的 Prometheus 配置如下：

```yaml
scrape_configs:
  - job_name: 'my-nezha-exporter'  # 这就是您的 job 名称
    static_configs:
      - targets: ['localhost:9100']
```

则需要将 `job` 变量设置为 `my-nezha-exporter`。

## 主仪表板功能 (Nezha-grafana.json)

- CPU 使用率监控
- 内存使用率监控
- 磁盘使用率监控
- 网络流量监控（上传/下载速度和流量）
- 进程数监控
- TCP/UDP 连接数监控
- 交换空间使用率
- 系统运行时长
- 温度监控
- **服务监控**（按服务器展示各监控节点的延迟数据）

### 主仪表板变量说明

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `job` | Prometheus job 名称 | `nezhav1` |
| `group` | 服务器分组筛选 | 全部 |
| `name` | 服务器名称筛选 | 全部 |
| `avg_over_time` | 数据平均时间窗口 | `5m` |

## 服务监控仪表板功能 (Nezha_service.json)

专注于网络延迟监控，提供按分组和监控节点维度的数据展示：

- 按分组（group）分行展示
- 按监控节点（monitor_name）分列展示
- 每个面板显示该监控节点到各服务器的延迟数据

### 服务监控仪表板变量说明

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `job` | Prometheus job 名称（导入时配置） | `nezhav1` |
| `group` | 服务器分组筛选（支持多选） | 无默认值 |
| `monitor_name` | 监控节点名称筛选（支持多选） | 全部 |
| `avg_over_time` | 数据平均时间窗口 | `1m` |

### 两个仪表板的区别

| 特性 | 主仪表板 | 服务监控仪表板 |
|------|----------|----------------|
| 展示维度 | 按服务器展示 | 按分组和监控节点展示 |
| 数据内容 | 完整的服务器监控数据 + 服务延迟 | 仅服务延迟数据 |
| 重复面板 | 按服务器名称重复 | 按分组行重复 + 按监控节点列重复 |
| 适用场景 | 综合监控、查看单台服务器 | 专注网络质量分析、对比各监控节点 |