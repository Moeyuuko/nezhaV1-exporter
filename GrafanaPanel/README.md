# Nezha Grafana Dashboard

这是 nezha-exporter 的 Grafana 仪表板配置文件。

## 导入说明

1. 在 Grafana 中，进入 **Dashboards** → **Import**
2. 上传 `Nezha-grafana.json` 文件或粘贴其内容
3. 选择对应的 Prometheus 数据源

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

## 仪表板功能

- CPU 使用率监控
- 内存使用率监控
- 磁盘使用率监控
- 网络流量监控（上传/下载速度和流量）
- 进程数监控
- TCP/UDP 连接数监控
- 交换空间使用率
- 系统运行时长
- 温度监控

## 变量说明

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `job` | Prometheus job 名称 | `nezhav1` |
| `group` | 服务器分组筛选 | 全部 |
| `name` | 服务器名称筛选 | 全部 |
| `avg_over_time` | 数据平均时间窗口 | `5m` |