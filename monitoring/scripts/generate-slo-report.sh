#!/bin/bash
# ============================================
# SLO 合规报告生成脚本
# 用于决策与反馈层 - 持续改进
# ============================================

PROMETHEUS_URL="http://prometheus:9090"
REPORT_DIR="/reports"
TIMESTAMP=$(date -Iseconds)
DATE=$(date +%Y%m%d)

echo "=========================================="
echo "SLO 合规报告生成 - $TIMESTAMP"
echo "=========================================="

# 创建报告目录
mkdir -p "$REPORT_DIR"

# 查询 Prometheus 获取 SLO 指标
query_prometheus() {
    local query="$1"
    curl -s "${PROMETHEUS_URL}/api/v1/query?query=${query}" | jq -r '.data.result[0].value[1] // "N/A"'
}

# 获取各项指标
echo "正在收集指标..."

AVAILABILITY=$(query_prometheus "slo:availability:ratio_1h")
LATENCY_P95=$(query_prometheus "slo:latency:p95_5m")
ERROR_RATE=$(query_prometheus "slo:error_rate:ratio_5m")
REQUEST_RATE=$(query_prometheus "sum(rate(gateway_requests_total[5m]))")
ACTIVE_ALERTS=$(query_prometheus "count(ALERTS{alertstate=\"firing\"})")

# 判断 SLO 合规性
check_slo() {
    local metric="$1"
    local threshold="$2"
    local comparison="$3"
    
    if [ "$metric" = "N/A" ] || [ -z "$metric" ]; then
        echo "unknown"
        return
    fi
    
    if [ "$comparison" = "lt" ]; then
        if (( $(echo "$metric < $threshold" | bc -l) )); then
            echo "breached"
        else
            echo "compliant"
        fi
    else
        if (( $(echo "$metric > $threshold" | bc -l) )); then
            echo "breached"
        else
            echo "compliant"
        fi
    fi
}

AVAILABILITY_STATUS=$(check_slo "$AVAILABILITY" "0.999" "lt")
LATENCY_STATUS=$(check_slo "$LATENCY_P95" "0.5" "gt")
ERROR_STATUS=$(check_slo "$ERROR_RATE" "0.001" "gt")

# 生成 JSON 报告
cat > "$REPORT_DIR/slo-report-${DATE}.json" << EOF
{
  "report_metadata": {
    "generated_at": "$TIMESTAMP",
    "report_type": "SLO_COMPLIANCE",
    "version": "1.0"
  },
  "slo_compliance": {
    "availability": {
      "target": "99.9%",
      "current": "$AVAILABILITY",
      "status": "$AVAILABILITY_STATUS"
    },
    "latency_p95": {
      "target": "<500ms",
      "current": "${LATENCY_P95}s",
      "status": "$LATENCY_STATUS"
    },
    "error_rate": {
      "target": "<0.1%",
      "current": "$ERROR_RATE",
      "status": "$ERROR_STATUS"
    }
  },
  "system_health": {
    "request_rate": "$REQUEST_RATE",
    "active_alerts": "$ACTIVE_ALERTS"
  },
  "recommendations": []
}
EOF

# 添加改进建议
RECOMMENDATIONS="[]"

if [ "$AVAILABILITY_STATUS" = "breached" ]; then
    RECOMMENDATIONS=$(echo "$RECOMMENDATIONS" | jq '. + ["可用性低于SLO目标，建议检查服务健康状态"]')
fi

if [ "$LATENCY_STATUS" = "breached" ]; then
    RECOMMENDATIONS=$(echo "$RECOMMENDATIONS" | jq '. + ["延迟超过SLO目标，建议优化慢查询或扩容"]')
fi

if [ "$ERROR_STATUS" = "breached" ]; then
    RECOMMENDATIONS=$(echo "$RECOMMENDATIONS" | jq '. + ["错误率超过SLO目标，建议检查错误日志"]')
fi

# 更新报告中的建议
jq --argjson recs "$RECOMMENDATIONS" '.recommendations = $recs' "$REPORT_DIR/slo-report-${DATE}.json" > "$REPORT_DIR/temp.json" && mv "$REPORT_DIR/temp.json" "$REPORT_DIR/slo-report-${DATE}.json"

# 创建最新报告的软链接
ln -sf "$REPORT_DIR/slo-report-${DATE}.json" "$REPORT_DIR/latest.json"

echo "报告已生成: $REPORT_DIR/slo-report-${DATE}.json"
echo ""
echo "SLO 合规状态:"
echo "  - 可用性: $AVAILABILITY_STATUS ($AVAILABILITY)"
echo "  - 延迟: $LATENCY_STATUS (${LATENCY_P95}s)"
echo "  - 错误率: $ERROR_STATUS ($ERROR_RATE)"
echo "=========================================="
