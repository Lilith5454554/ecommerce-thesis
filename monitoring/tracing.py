"""
OpenTelemetry 分布式链路追踪配置
非侵入式设计 - 通过导入此模块即可启用追踪
"""
import os
from functools import wraps

# 尝试导入OpenTelemetry，如果未安装则提供空实现
try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.trace.status import Status, StatusCode
    
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    print("Warning: OpenTelemetry not installed. Tracing disabled.")


def init_tracing(service_name: str, app=None, engine=None):
    """
    初始化链路追踪
    
    Args:
        service_name: 服务名称 (如: user-service, order-service)
        app: FastAPI应用实例
        engine: SQLAlchemy引擎实例
    """
    if not TRACING_AVAILABLE:
        return None
    
    # 配置OTLP导出器 (发送到Jaeger)
    jaeger_endpoint = os.getenv("JAEGER_ENDPOINT", "http://jaeger:4318/v1/traces")
    
    # 创建资源
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: "1.0.0",
        "deployment.environment": os.getenv("ENV", "development")
    })
    
    # 创建Provider
    provider = TracerProvider(resource=resource)
    
    # 配置OTLP导出器
    otlp_exporter = OTLPSpanExporter(endpoint=jaeger_endpoint)
    span_processor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(span_processor)
    
    # 设置为全局Provider
    trace.set_tracer_provider(provider)
    
    # 自动 instrument FastAPI
    if app:
        FastAPIInstrumentor.instrument_app(app)
    
    # 自动 instrument HTTPX (HTTP客户端)
    HTTPXClientInstrumentor().instrument()
    
    # 自动 instrument SQLAlchemy
    if engine:
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            enable_commenter=True,
        )
    
    print(f"✓ Tracing initialized for {service_name}")
    return provider


def get_tracer(name: str):
    """获取tracer实例"""
    if not TRACING_AVAILABLE:
        return None
    return trace.get_tracer(name)


def trace_span(span_name: str, attributes: dict = None):
    """
    装饰器：为函数添加自定义span
    
    使用示例:
        @trace_span("process_order", {"operation": "create"})
        async def create_order(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not TRACING_AVAILABLE:
                return await func(*args, **kwargs)
            
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not TRACING_AVAILABLE:
                return func(*args, **kwargs)
            
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


# 导入asyncio用于检测
import asyncio
