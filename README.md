# 电商平台微服务系统

基于微服务架构的电商系统，集成完整的可观测性平台（Observability Stack）。

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端层                                 │
│                    (frontend/)                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      API 网关层                              │
│              (api_gateway/ - FastAPI)                       │
│  • JWT认证  • 请求路由  • 限流  • 监控埋点                    │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   用户服务       │ │   商品服务       │ │   订单服务       │
│ user_service/   │ │ product_service/│ │  order_service/ │
│                 │ │                 │ │                 │
│ • 注册/登录      │ │ • 商品CRUD      │ │ • 订单创建      │
│ • JWT令牌       │ │ • 库存管理      │ │ • Saga事务      │
│ • 用户管理      │ │ • 库存预留      │ │ • 超时取消      │
└─────────────────┘ └─────────────────┘ └─────────────────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    基础设施层                                │
│  • PostgreSQL (数据库)    • Redis (缓存)                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              可观测性平台 (Observability)                    │
├─────────────────────────────────────────────────────────────┤
│  • Prometheus  - 指标收集                                    │
│  • Grafana     - 可视化仪表板                                │
│  • Jaeger      - 分布式链路追踪                              │
│  • AlertManager- 告警管理                                    │
│  • SLO报告     - 持续改进                                    │
└─────────────────────────────────────────────────────────────┘
```

## 核心特性

### 微服务架构
- **API 网关**: 统一入口，JWT认证，请求转发
- **用户服务**: 用户注册、登录、JWT令牌管理
- **商品服务**: 商品CRUD、库存预留/释放
- **订单服务**: 订单创建、Saga分布式事务、自动取消

### 可观测性三大支柱

#### 1. Metrics（指标）✅
- Prometheus 采集全链路指标
- 自定义业务指标（订单、用户、库存）
- SLO 合规性指标

#### 2. Logs（日志）⚠️
- 基础日志输出
- 可扩展集中式日志（Loki预留）

#### 3. Traces（链路追踪）✅
- OpenTelemetry + Jaeger
- 自动追踪跨服务调用
- 性能瓶颈定位

### SLO 服务等级目标

| 指标 | 目标 | 实现方式 |
|------|------|----------|
| 可用性 | 99.9% | Prometheus + 告警规则 |
| 延迟(P95) | < 500ms | Histogram + Grafana |
| 错误率 | < 0.1% | Counter + AlertManager |

## 快速开始

### 环境要求
- Docker & Docker Compose
- Python 3.9+ (本地开发)

### 启动系统

```bash
# 克隆项目
git clone <repository-url>
cd ecommerce-thesis

# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps
```

### 访问服务

| 服务 | URL | 说明 |
|------|-----|------|
| 前端演示 | http://localhost:8000/frontend | 电商演示页面 |
| API 网关 | http://localhost:8000 | API入口 |
| Prometheus | http://localhost:9090 | 指标查询 |
| Grafana | http://localhost:3000 | 可视化 (admin/admin) |
| Jaeger UI | http://localhost:16686 | 链路追踪 |
| AlertManager | http://localhost:9093 | 告警管理 |

### 前端演示

打开 http://localhost:8000/frontend 体验：
1. 用户注册/登录
2. 浏览商品列表
3. 创建订单（需登录）
4. 查看订单列表
5. 取消订单

## 项目结构

```
ecommerce-thesis/
├── api_gateway/              # API网关
│   ├── main.py              # 网关主程序
│   ├── requirements.txt     # 依赖
│   └── Dockerfile           # 容器配置
│
├── user_service/            # 用户服务
│   ├── main.py
│   ├── models.py            # 数据库模型
│   └── tests/               # 单元测试
│
├── product_service/         # 商品服务
│   ├── main.py
│   ├── models.py
│   └── saga.py              # Saga事务
│
├── order_service/           # 订单服务
│   ├── main.py
│   ├── models.py
│   └── saga.py              # Saga事务编排
│
├── frontend/                # 前端演示
│   ├── index.html
│   ├── script.js
│   └── style.css
│
├── monitoring/              # 可观测性平台 ⭐
│   ├── prometheus.yml       # Prometheus配置
│   ├── prometheus-alerts.yml # SLO告警规则
│   ├── alertmanager.yml     # 告警路由
│   ├── grafana-dashboards/  # 预置仪表板
│   │   ├── slo-dashboard.json
│   │   └── service-overview.json
│   ├── grafana-datasources.yml
│   ├── tracing.py           # OpenTelemetry配置
│   ├── scripts/             # SLO报告脚本
│   └── README.md            # 可观测性文档
│
├── docker-compose.yml       # 容器编排
└── README.md               # 本文件
```

## 可观测性平台详解

### 1. 指标收集 (Prometheus)

各服务暴露 `/metrics` 端点，Prometheus 定期抓取：

```python
# 示例：自定义业务指标
from prometheus_client import Counter, Histogram

orders_created = Counter('orders_created_total', 'Total orders created')
request_latency = Histogram('request_duration_seconds', 'Request latency')
```

### 2. 链路追踪 (Jaeger)

自动追踪跨服务调用，无需修改业务代码：

```python
# 自动 instrument
from tracing import init_tracing
init_tracing("service-name", app=app)
```

在 Jaeger UI 查看完整调用链：
- 请求路径：gateway -> user-service -> order-service
- 每个服务的处理时间
- 错误发生的具体位置

### 3. SLO 监控 (Grafana)

预置仪表板：
- **SLO Dashboard**: 实时显示可用性、延迟、错误率
- **Service Overview**: 各服务指标概览

### 4. 告警管理 (AlertManager)

告警规则：
- 可用性 < 99.9% → 严重告警
- 延迟 > 500ms → 严重告警
- 错误率 > 0.1% → 严重告警

### 5. 持续改进 (SLO报告)

自动生成 SLO 合规报告：

```bash
# 手动生成报告
docker-compose exec slo-reporter /scripts/generate-slo-report.sh

# 查看报告
cat monitoring/slo-reports/latest.json
```

## 开发指南

### 本地开发

```bash
# 进入服务目录
cd user_service

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 运行服务
uvicorn main:app --reload --port 8001
```

### 运行测试

```bash
# 测试用户服务
cd user_service
pytest tests/ -v --cov=./

# 测试所有服务
docker-compose -f docker-compose.test.yml up
```

### 添加新服务

1. 创建服务目录
2. 添加 `main.py`、`requirements.txt`、`Dockerfile`
3. 在 `docker-compose.yml` 中添加服务配置
4. 在 `monitoring/prometheus.yml` 中添加抓取配置
5. 添加链路追踪初始化代码

## 技术栈

### 后端
- **FastAPI**: Web框架
- **SQLAlchemy**: ORM
- **PostgreSQL**: 数据库
- **Redis**: 缓存
- **HTTPX**: 异步HTTP客户端
- **Passlib**: 密码加密
- **python-jose**: JWT处理

### 可观测性
- **Prometheus**: 指标收集
- **Grafana**: 可视化
- **Jaeger**: 链路追踪
- **OpenTelemetry**: 追踪SDK
- **AlertManager**: 告警管理

### 基础设施
- **Docker**: 容器化
- **Docker Compose**: 本地编排

## 架构决策

### 为什么选择 Saga 模式？

订单创建涉及多个服务：
1. 预留库存（商品服务）
2. 创建订单（订单服务）

如果订单创建失败，需要释放已预留的库存。Saga模式通过补偿操作保证最终一致性。

### 可观测性设计原则

1. **非侵入式**: 通过中间件和自动instrument实现，不修改业务逻辑
2. **统一标准**: 使用 OpenTelemetry 标准，避免厂商锁定
3. **SLO驱动**: 基于服务等级目标定义告警，而非随意阈值
4. **可行动**: 告警包含上下文和改进建议

## 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 许可证

MIT License

## 联系方式

如有问题，请提交 Issue 或联系维护者。

---

**文档版本**: 1.0  
**最后更新**: 2024
