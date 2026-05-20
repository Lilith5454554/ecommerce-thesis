# 电商平台可观测性平台

本目录包含完整的可观测性（Observability）解决方案，实现 Metrics、Logs、Traces 三大支柱，以及 SLO 驱动的持续改进机制。

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    可观测性平台 (Observability Stack)          │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Metrics  │  │  Logs    │  │  Traces  │  │  Alerts  │    │
│  │Prometheus│  │  (预留)  │  │  Jaeger  │  │AlertMgr  │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │             │             │             │          │
│       └─────────────┴──────┬──────┴─────────────┘          │
│                            │                                │
│                     ┌──────┴──────┐                        │
│                     │   Grafana   │  ← 统一可视化平台       │
│                     └─────────────┘                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              决策与反馈层 (Decision & Feedback)               │
├─────────────────────────────────────────────────────────────┤
│  • SLO 合规报告生成                                          │
│  • 自动告警与通知                                            │
│  • 持续改进建议                                              │
└─────────────────────────────────────────────────────────────┘
```

## 三大支柱实现

### 1. Metrics（指标）- ✅ 已实现

**Prometheus** 采集以下指标：

| 指标类型 | 说明 | 示例 |
|---------|------|------|
| 请求指标 | 请求数、延迟、错误率 | `gateway_requests_total` |
| 业务指标 | 订单、用户、商品统计 | `orders_created_total` |
| 资源指标 | CPU、内存使用 | `gateway_cpu_usage_percent` |
| SLO指标 | 可用性、延迟合规性 | `slo:availability:ratio_5m` |

**访问地址**: http://localhost:9090

### 2. Logs（日志）- ⚠️ 基础实现

各服务已配置基础日志输出，集中式日志收集（如 Loki）可后续扩展。

### 3. Traces（链路追踪）- ✅ 已实现

**Jaeger** 实现分布式链路追踪：
- 自动追踪跨服务调用
- 性能瓶颈定位
- 错误根因分析

**访问地址**: http://localhost:16686

## SLO（服务等级目标）

### 定义的 SLO

| SLO | 目标值 | 测量方式 |
|-----|--------|----------|
| 可用性 | 99.9% | 成功请求数 / 总请求数 |
| 延迟 (P95) | < 500ms | 95% 的请求响应时间 |
| 错误率 | < 0.1% | 5xx错误数 / 总请求数 |

### 告警规则

配置在 `prometheus-alerts.yml` 中：

- **严重告警**: 可用性 < 99.9%，延迟 > 500ms，错误率 > 0.1%
- **警告**: 指标接近 SLO 阈值
- **信息**: 慢请求检测等

### 告警通知

**AlertManager** 配置路由规则：
- 严重告警 → 立即通知
- SLO告警 → SLO团队
- 业务告警 → 业务团队

**访问地址**: http://localhost:9093

## Grafana 仪表板

### 预置仪表板

1. **SLO 服务等级目标监控** (`slo-dashboard.json`)
   - SLO 三大支柱实时状态
   - 可用性、延迟、错误率趋势
   - 当前告警列表

2. **服务整体概览** (`service-overview.json`)
   - 各服务请求速率
   - 延迟分布 (P50/P95)
   - 业务指标（用户数、商品数、订单数）

**访问地址**: http://localhost:3000
- 用户名: `admin`
- 密码: `admin`

## 决策与反馈层

### SLO 报告生成

脚本位置: `scripts/generate-slo-report.sh`

功能：
- 定期生成 SLO 合规报告
- 自动识别 SLO 违规情况
- 提供改进建议

报告位置: `slo-reports/slo-report-YYYYMMDD.json`

### 持续改进流程

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  收集指标  │ -> │  SLO评估  │ -> │  生成报告  │ -> │  改进措施  │
│Prometheus│    │  告警规则  │    │  建议生成  │    │  迭代优化  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

## 快速开始

### 启动完整可观测性平台

```bash
# 启动所有服务（包括可观测性组件）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f prometheus
docker-compose logs -f grafana
docker-compose logs -f jaeger
```

### 访问各组件

| 组件 | URL | 说明 |
|------|-----|------|
| API 网关 | http://localhost:8000 | 应用入口 |
| Prometheus | http://localhost:9090 | 指标查询 |
| Grafana | http://localhost:3000 | 可视化 (admin/admin) |
| AlertManager | http://localhost:9093 | 告警管理 |
| Jaeger UI | http://localhost:16686 | 链路追踪 |

### 生成 SLO 报告

```bash
# 手动生成报告
docker-compose exec slo-reporter /scripts/generate-slo-report.sh

# 查看报告
cat monitoring/slo-reports/latest.json
```

## 配置说明

### 添加新的告警规则

编辑 `prometheus-alerts.yml`，添加新的规则组：

```yaml
groups:
  - name: my_new_rules
    rules:
      - alert: MyAlert
        expr: my_metric > threshold
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "告警摘要"
          description: "告警详情"
```

重载 Prometheus 配置：
```bash
curl -X POST http://localhost:9090/-/reload
```

### 自定义 SLO 目标

编辑 `prometheus-alerts.yml` 中的阈值：

```yaml
# 修改 SLO 目标值
- record: slo:availability:ratio_5m
  expr: ...
  labels:
    slo_target: "0.995"  # 修改为 99.5%
```

## 故障排查

### 常见问题

1. **Jaeger 无法接收追踪数据**
   - 检查服务环境变量 `JAEGER_ENDPOINT`
   - 确认 Jaeger 容器运行状态

2. **Prometheus 无法抓取指标**
   - 检查服务 `/metrics` 端点是否可访问
   - 查看 Prometheus Targets 页面

3. **Grafana 没有数据**
   - 确认 Prometheus 数据源配置
   - 检查仪表板查询语句

## 扩展计划

- [ ] 集成 Loki 实现集中式日志收集
- [ ] 添加更多业务指标仪表板
- [ ] 实现自动化 SLO 报告邮件发送
- [ ] 添加性能基线对比功能
