from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timezone
from app.database import Base


class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")  # admin/user
    status = Column(String(20), nullable=False, default="active")  # active/disabled
    pc_identifier = Column(String(255), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    devices = relationship("Device", back_populates="owner")
    tasks = relationship("TestTask", back_populates="user")
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"


class Device(Base):
    """设备表"""
    __tablename__ = "devices"
    
    id = Column(Integer, primary_key=True, index=True)
    serial_number = Column(String(100), unique=True, nullable=False, index=True)
    model = Column(String(100), nullable=True)
    brand = Column(String(50), nullable=True)
    android_version = Column(String(20), nullable=True)
    sdk_version = Column(String(10), nullable=True)
    cpu_abi = Column(String(50), nullable=True)
    resolution = Column(String(20), nullable=True)
    battery_level = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="offline")  # online/offline/testing
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    pc_identifier = Column(String(255), nullable=False)
    # 乐观并发版本（设备改派契约 §2/§6）：从 1 开始，条件更新时递增
    version = Column(Integer, nullable=False, default=1, server_default="1")
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 硬件画像扩展字段
    board = Column(String(50), nullable=True)  # 主板平台，如 rk3568 / a133p
    hardware = Column(String(50), nullable=True)  # 硬件名称
    ddr_info = Column(JSON, nullable=True)  # DDR 信息：容量、频率等
    emmc_info = Column(JSON, nullable=True)  # EMMC 信息：容量、型号、健康状态
    wifi_chip = Column(String(100), nullable=True)  # WIFI 芯片型号
    bt_chip = Column(String(100), nullable=True)  # 蓝牙芯片型号
    eth_interfaces = Column(JSON, nullable=True)  # 以太网接口列表
    features = Column(JSON, nullable=True)  # 设备能力特征：wifi/bt/eth 等
    
    # 关系
    owner = relationship("User", back_populates="devices")
    tasks = relationship("TestTask", back_populates="device")
    
    def __repr__(self):
        return f"<Device(id={self.id}, serial={self.serial_number}, status={self.status})>"


class TestTool(Base):
    """测试工具表"""
    __tablename__ = "test_tools"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    filename = Column(String(255), nullable=False)
    version = Column(String(50), nullable=True)
    architecture = Column(String(50), nullable=True)  # arm64-v8a/armeabi-v7a
    file_size = Column(Integer, nullable=False)
    file_path = Column(String(500), nullable=False)
    mime_type = Column(String(100), nullable=True)
    md5_hash = Column(String(32), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    test_items = relationship("TestItem", back_populates="tool")
    
    def __repr__(self):
        return f"<TestTool(id={self.id}, name={self.name})>"


class TestModule(Base):
    """测试模块表"""
    __tablename__ = "test_modules"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True)
    sort_order = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    items = relationship("TestItem", back_populates="module", order_by="TestItem.sort_order")
    
    def __repr__(self):
        return f"<TestModule(id={self.id}, name={self.name})>"


class TestItem(Base):
    """测试项表"""
    __tablename__ = "test_items"
    
    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("test_modules.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    objective = Column(Text, nullable=True)  # 测试目的
    precondition = Column(Text, nullable=True)  # 前置条件
    steps = Column(Text, nullable=True)  # 测试步骤
    expected_result = Column(Text, nullable=True)  # 预期结果
    sort_order = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)

    # 执行配置
    exec_type = Column(String(20), nullable=False)  # adb_shell/push_exec/host_exec
    exec_command = Column(Text, nullable=False)
    tool_id = Column(Integer, ForeignKey("test_tools.id"), nullable=True)
    push_target = Column(String(255), nullable=True)
    parameters = Column(JSON, default=dict)
    parameters_schema = Column(JSON, nullable=True)
    
    # 兼容性配置
    compatibility = Column(JSON, default=dict)

    # 判定方式与规则
    judgement_type = Column(String(20), default="assertion")  # assertion/rubric/ai_fallback
    conditional_rules = Column(JSON, nullable=True)  # 条件式断言规则
    rubric_criteria = Column(JSON, nullable=True)  # Rubrics 评分标准

    # 结果解析配置
    result_parse = Column(JSON, default=dict)
    timeout = Column(Integer, default=300)
    on_failure = Column(String(20), default="continue")  # continue/stop
    retry_count = Column(Integer, default=0)

    # 执行技能与标签
    skills = Column(JSON, nullable=True)  # 关联 Skill ID 列表
    tags = Column(JSON, nullable=True)  # 测试类型标签：functional/performance/stability/stress
    
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    module = relationship("TestModule", back_populates="items")
    tool = relationship("TestTool", back_populates="test_items")
    records = relationship("TestRecord", back_populates="item")
    baselines = relationship("Baseline", back_populates="item")
    golden_cases = relationship("GoldenCase", back_populates="item")

    def __repr__(self):
        return f"<TestItem(id={self.id}, name={self.name}, type={self.exec_type})>"


class TestTask(Base):
    """测试任务表

    task_kind：instance（普通执行实例，含 immediate/once）/ daily_template
    （每日定时模板，不直接执行，由调度器按 scheduled_for 生成实例）；
    daily 实例通过 template_id + scheduled_for 回溯模板与计划时刻。
    """
    __tablename__ = "test_tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    name = Column(String(200), nullable=True)
    selected_items = Column(JSON, nullable=False)  # 选中的测试项ID列表
    custom_parameters = Column(JSON, default=dict)
    status = Column(String(20), nullable=False, default="pending")  # pending/running/completed/failed/cancelled
    progress_percent = Column(Integer, default=0)
    plan = Column(JSON, nullable=True)  # AI 自然语言规划结果快照
    report_path = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    # 调度配置：immediate 立即执行；once 定时一次；daily 每日定时
    schedule_type = Column(String(20), nullable=False, default="immediate")  # immediate/once/daily
    scheduled_time = Column(String(50), nullable=True)  # once: "YYYY-MM-DD HH:MM"；daily: "HH:MM"（服务器本地时间）
    next_run_at = Column(DateTime(timezone=True), nullable=True)  # 调度器计算的下次触发时间
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # 软删除标记（契约 task-execution §8）：终态任务删除时写入 UTC 时间；
    # 默认列表排除非空值，记录/报告引用保留可追溯。由 004_task_deleted_at 迁移提供。
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    # daily 模板/实例（R16/R17，005_daily_task_templates）：模板不执行、不进执行统计；
    # 实例的 scheduled_for 为 UTC 计划时刻，唯一索引保证同模板同时刻至多一个实例。
    task_kind = Column(
        String(20), nullable=False, default="instance", server_default="instance"
    )  # instance/daily_template（server_default 与 005 迁移 DDL 指纹对齐）
    template_id = Column(Integer, ForeignKey("test_tasks.id"), nullable=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    # 创建时测试项执行配置快照（R20）：历史无快照任务为 legacy，不得反填冒充
    item_snapshot = Column(JSON, nullable=True)
    item_snapshot_status = Column(String(20), nullable=True)  # complete/legacy

    # 关系
    user = relationship("User", back_populates="tasks")
    device = relationship("Device", back_populates="tasks")
    records = relationship("TestRecord", back_populates="task")
    # daily 模板 → 实例（非外键硬约束的视图关系，实例侧 template_id 自引用）
    template = relationship("TestTask", remote_side=[id], foreign_keys=[template_id])

    # 与 005 迁移的 CREATE UNIQUE INDEX / 索引 DDL 指纹一致
    # （SQLite 下唯一索引 ⇔ 表级唯一约束；ix_test_tasks_task_kind 为列表过滤索引）
    __table_args__ = (
        Index(
            "uq_task_template_scheduled_for",
            "template_id",
            "scheduled_for",
            unique=True,
        ),
        Index("ix_test_tasks_task_kind", "task_kind"),
    )
    
    def __repr__(self):
        return f"<TestTask(id={self.id}, status={self.status})>"


class TestRecord(Base):
    """测试记录表"""
    __tablename__ = "test_records"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("test_tasks.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("test_items.id"), nullable=False)
    status = Column(String(20), nullable=False)  # pending/running/pass/fail/skip/error/timeout
    output = Column(Text, nullable=True)
    fail_reason = Column(Text, nullable=True)
    extracted_data = Column(JSON, nullable=True)
    execution_time = Column(Integer, nullable=True)  # 秒
    log_file_path = Column(String(500), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    task = relationship("TestTask", back_populates="records")
    item = relationship("TestItem", back_populates="records")
    
    def __repr__(self):
        return f"<TestRecord(id={self.id}, task_id={self.task_id}, status={self.status})>"


class FailurePattern(Base):
    """失败模式库：用于自动归类测试失败原因。"""
    __tablename__ = "failure_patterns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True)  # adb/compat/timeout/assertion
    pattern = Column(String(500), nullable=False)  # 正则表达式
    description = Column(Text, nullable=True)
    suggested_fix = Column(Text, nullable=True)
    occurrence_count = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<FailurePattern(id={self.id}, name={self.name})>"


class Baseline(Base):
    """统计基线：按设备型号和测试项聚合历史指标。"""
    __tablename__ = "baselines"

    id = Column(Integer, primary_key=True, index=True)
    device_model = Column(String(100), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("test_items.id"), nullable=False)
    metric_name = Column(String(100), nullable=False)
    avg_value = Column(String(50), nullable=True)
    min_value = Column(String(50), nullable=True)
    max_value = Column(String(50), nullable=True)
    sample_count = Column(Integer, default=0)
    last_record_id = Column(Integer, ForeignKey("test_records.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    item = relationship("TestItem", back_populates="baselines")

    def __repr__(self):
        return f"<Baseline(id={self.id}, model={self.device_model}, metric={self.metric_name})>"


class GoldenCase(Base):
    """黄金案例：同一测试项在同一型号设备上的标准通过输出。"""
    __tablename__ = "golden_cases"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("test_items.id"), nullable=False)
    device_model = Column(String(100), nullable=False, index=True)
    expected_status = Column(String(20), nullable=False, default="pass")
    expected_output_pattern = Column(String(500), nullable=True)  # 正则
    sample_output = Column(Text, nullable=True)  # 最近一次通过的原始输出摘要
    pass_count = Column(Integer, default=0)
    total_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    item = relationship("TestItem", back_populates="golden_cases")

    def __repr__(self):
        return f"<GoldenCase(id={self.id}, item_id={self.item_id}, model={self.device_model})>"


class KnowledgeEntry(Base):
    """测试知识库条目：支持资料、测试用例、规则、失败模式、基线、技能等多种类型。"""
    __tablename__ = "knowledge_entries"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    entry_type = Column(String(50), nullable=False, default="document")  # document/test_case/device_profile/rule/failure_pattern/baseline/skill
    category = Column(String(100), nullable=True)
    tags = Column(JSON, default=list)
    content = Column(Text, nullable=True)  # 原始文本内容
    chunks = Column(JSON, nullable=True)  # 文档分片，用于检索
    embedding = Column(JSON, nullable=True)  # 向量嵌入（余弦相似度检索）
    source_type = Column(String(50), nullable=False, default="manual")  # manual/upload/ai_extracted/test_feedback
    source_file = Column(String(500), nullable=True)  # 上传文件路径
    status = Column(String(50), nullable=False, default="draft")  # draft/approved/rejected/deprecated
    meta = Column("metadata", JSON, default=dict)  # 扩展字段：作者、版本、关联设备型号、关联测试项ID等
    pass_count = Column(Integer, default=0)  # 执行通过次数（test_feedback 时更新）
    fail_count = Column(Integer, default=0)  # 执行失败次数
    hit_count = Column(Integer, default=0)  # 检索/命中次数
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    creator = relationship("User")

    def __repr__(self):
        return f"<KnowledgeEntry(id={self.id}, title={self.title}, type={self.entry_type})>"


class IdempotencyRecord(Base):
    """写操作幂等记录：保存 (user_id, operation, idempotency_key) 的首次响应。

    契约 docs/contracts/README.md 第 3 节：任务创建与失败重跑使用
    Idempotency-Key；UNIQUE(user_id, operation, idempotency_key) 由数据库
    唯一约束兜底并发重复，同一键不同请求体返回 409（request_sha256 比对）。
    """
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "operation", "idempotency_key",
            name="uq_idempotency_user_op_key",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    operation = Column(String(50), nullable=False)  # task_create / task_rerun 等
    idempotency_key = Column(String(128), nullable=False)
    request_sha256 = Column(String(64), nullable=False)  # 规范化请求体摘要
    response_json = Column(JSON, nullable=True)  # 首次成功响应（None=仍在执行中）
    task_id = Column(Integer, ForeignKey("test_tasks.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return (
            f"<IdempotencyRecord(id={self.id}, user_id={self.user_id}, "
            f"operation={self.operation}, key={self.idempotency_key})>"
        )
