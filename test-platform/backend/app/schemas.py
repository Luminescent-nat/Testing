from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ========== 用户模块 ==========

class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.ACTIVE


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=32)
    pc_identifier: Optional[str] = None


class UserUpdate(BaseModel):
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None


class UserResponse(UserBase):
    id: int
    pc_identifier: Optional[str]
    last_login_at: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


# ========== 设备模块 ==========

class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    TESTING = "testing"


class DeviceBase(BaseModel):
    serial_number: str
    model: Optional[str] = None
    brand: Optional[str] = None
    android_version: Optional[str] = None
    sdk_version: Optional[str] = None
    cpu_abi: Optional[str] = None
    resolution: Optional[str] = None
    battery_level: Optional[int] = Field(None, ge=0, le=100)
    board: Optional[str] = None
    hardware: Optional[str] = None
    ddr_info: Optional[Dict[str, Any]] = None
    emmc_info: Optional[Dict[str, Any]] = None
    wifi_chip: Optional[str] = None
    bt_chip: Optional[str] = None
    eth_interfaces: Optional[List[str]] = None
    features: Optional[List[str]] = None


class DeviceCreate(DeviceBase):
    owner_id: Optional[int] = None
    pc_identifier: str


class DeviceUpdate(BaseModel):
    status: Optional[DeviceStatus] = None
    battery_level: Optional[int] = Field(None, ge=0, le=100)


class DeviceResponse(DeviceBase):
    id: int
    status: DeviceStatus
    owner_id: Optional[int]
    pc_identifier: str
    last_seen_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class DeviceList(BaseModel):
    items: List[DeviceResponse]
    total: int


# ========== 测试工具模块 ==========

class TestToolBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    version: Optional[str] = Field(None, max_length=50)
    architecture: Optional[str] = Field(None, max_length=50)


class TestToolCreate(TestToolBase):
    pass


class TestToolResponse(TestToolBase):
    id: int
    filename: str
    file_size: int
    file_path: str
    md5_hash: Optional[str]
    created_by: Optional[int]
    created_at: datetime
    
    class Config:
        from_attributes = True


class TestToolList(BaseModel):
    items: List[TestToolResponse]
    total: int


# ========== 测试模块 ==========

class TestModuleBase(BaseModel):
    name: str = Field(..., max_length=100)
    category: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=50)
    sort_order: int = 0
    enabled: bool = True


class TestModuleCreate(TestModuleBase):
    pass


class TestModuleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=50)
    sort_order: Optional[int] = None
    enabled: Optional[bool] = None


class TestModuleResponse(TestModuleBase):
    id: int
    item_count: int = 0
    created_by: Optional[int]
    created_at: datetime
    
    class Config:
        from_attributes = True


class TestModuleList(BaseModel):
    items: List[TestModuleResponse]
    total: int


# ========== 测试项 ==========

class ExecType(str, Enum):
    ADB_SHELL = "adb_shell"
    PUSH_EXEC = "push_exec"
    HOST_EXEC = "host_exec"


class JudgementType(str, Enum):
    ASSERTION = "assertion"
    RUBRIC = "rubric"
    AI_FALLBACK = "ai_fallback"


class TestItemBase(BaseModel):
    module_id: int
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    objective: Optional[str] = None  # 测试目的
    precondition: Optional[str] = None  # 前置条件
    steps: Optional[str] = None  # 测试步骤
    expected_result: Optional[str] = None  # 预期结果
    sort_order: int = 0
    enabled: bool = True

    # 执行配置
    exec_type: ExecType
    exec_command: str
    tool_id: Optional[int] = None
    push_target: Optional[str] = Field(None, max_length=255)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    parameters_schema: Optional[Dict[str, Any]] = None

    # 兼容性配置
    compatibility: Dict[str, Any] = Field(default_factory=dict)

    # 判定方式与规则
    judgement_type: JudgementType = JudgementType.ASSERTION
    conditional_rules: Optional[Dict[str, Any]] = None
    rubric_criteria: Optional[Dict[str, Any]] = None

    # 结果解析配置
    result_parse: Dict[str, Any] = Field(default_factory=dict)
    timeout: int = Field(default=300, ge=10, le=7200)
    on_failure: str = Field(default="continue")  # continue/stop
    retry_count: int = Field(default=0, ge=0, le=5)

    # 执行技能与标签
    skills: Optional[List[str]] = None
    tags: Optional[List[str]] = None


class TestItemCreate(TestItemBase):
    pass


class TestItemUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    objective: Optional[str] = None
    precondition: Optional[str] = None
    steps: Optional[str] = None
    expected_result: Optional[str] = None
    enabled: Optional[bool] = None
    exec_type: Optional[ExecType] = None
    exec_command: Optional[str] = None
    tool_id: Optional[int] = None
    push_target: Optional[str] = Field(None, max_length=255)
    parameters: Optional[Dict[str, Any]] = None
    compatibility: Optional[Dict[str, Any]] = None
    judgement_type: Optional[JudgementType] = None
    conditional_rules: Optional[Dict[str, Any]] = None
    rubric_criteria: Optional[Dict[str, Any]] = None
    timeout: Optional[int] = Field(None, ge=10, le=7200)
    on_failure: Optional[str] = None
    retry_count: Optional[int] = Field(None, ge=0, le=5)
    skills: Optional[List[str]] = None
    tags: Optional[List[str]] = None


class TestItemResponse(TestItemBase):
    id: int
    created_by: Optional[int]
    created_at: datetime
    tool: Optional[TestToolResponse] = None

    class Config:
        from_attributes = True


class TestItemList(BaseModel):
    items: List[TestItemResponse]
    total: int


class TestModuleWithItems(TestModuleResponse):
    items: List[TestItemResponse] = []

    @model_validator(mode='after')
    def compute_item_count(self):
        self.item_count = len(self.items or [])
        return self


# ========== 测试任务 ==========

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduleType(str, Enum):
    IMMEDIATE = "immediate"
    ONCE = "once"
    DAILY = "daily"


class TestTaskBase(BaseModel):
    device_serial: str
    name: Optional[str] = Field(None, max_length=200)
    item_ids: List[int]
    custom_parameters: Dict[int, Dict[str, Any]] = Field(default_factory=dict)


class TestTaskCreate(BaseModel):
    device_serial: str
    name: Optional[str] = Field(None, max_length=200)
    item_ids: List[int]
    custom_parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    schedule_type: ScheduleType = ScheduleType.IMMEDIATE
    # once 传 "YYYY-MM-DD HH:MM"，daily 传 "HH:MM"（服务器本地时间），immediate 忽略
    scheduled_time: Optional[str] = None


class TestTaskResponse(BaseModel):
    id: int
    name: Optional[str]
    device_serial: Optional[str] = None
    status: TaskStatus
    progress_percent: int
    result: Optional[str] = None  # passed/failed/None(未出结果)
    schedule_type: str = "immediate"
    scheduled_time: Optional[str] = None
    next_run_at: Optional[datetime] = None
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    @field_validator("device_serial", mode="before")
    @classmethod
    def _extract_device_serial(cls, v, info):
        if v:
            return v
        device = info.data.get("device")
        return device.serial_number if device else None

    @model_validator(mode='before')
    @classmethod
    def compute_result(cls, data: Any):
        """根据测试记录计算任务级结果：有失败/错误/超时为 failed，否则有通过为 passed。

        仅从已加载（selectinload）的 records 关系读取，避免触发异步懒加载。
        """
        records = getattr(data, "__dict__", {}).get("records") if not isinstance(data, dict) else data.get("records")
        if records is not None and not getattr(data, "result", None):
            statuses = [r.status for r in records]
            if any(s in ("fail", "error", "timeout") for s in statuses):
                data.result = "failed"
            elif any(s == "pass" for s in statuses):
                data.result = "passed"
        return data
    
    class Config:
        from_attributes = True


class TestTaskDetail(TestTaskResponse):
    selected_items: List[int]
    custom_parameters: Dict[str, Any]
    error_message: Optional[str]
    plan: Optional[Dict[str, Any]] = None
    device: Optional[DeviceResponse] = None
    executor: Optional[dict] = None


class TestTaskList(BaseModel):
    items: List[TestTaskResponse]
    total: int


# ========== 测试记录 ==========

class RecordStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"
    TIMEOUT = "timeout"


class TestRecordResponse(BaseModel):
    id: int
    task_id: int
    item_id: int
    item_name: Optional[str] = None
    module_name: Optional[str] = None
    status: RecordStatus
    fail_reason: Optional[str]
    extracted_data: Optional[Dict[str, Any]]
    execution_time: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    @model_validator(mode='before')
    @classmethod
    def fill_names_from_relationships(cls, data: Any):
        """当 ORM 对象包含 item/module 关系时，自动填充 item_name/module_name。"""
        item = getattr(data, "item", None)
        if item is not None:
            if not getattr(data, "item_name", None):
                data.item_name = getattr(item, "name", None)
            module = getattr(item, "module", None)
            if module is not None and not getattr(data, "module_name", None):
                data.module_name = getattr(module, "name", None)
        return data

    class Config:
        from_attributes = True


class TestRecordDetail(TestRecordResponse):
    output: Optional[str]
    log_file_path: Optional[str] = None


# ========== 报告模块 ==========

class ReportSummary(BaseModel):
    total_items: int
    passed: int
    failed: int
    skipped: int
    pass_rate: str


class ReportResult(BaseModel):
    item_id: int
    item_name: str
    module_name: Optional[str]
    status: RecordStatus
    execution_time: Optional[int]
    fail_reason: Optional[str]
    extracted_data: Optional[Dict[str, Any]]
    output_summary: Optional[str]


class TestReport(BaseModel):
    report_version: str = "1.0"
    report_id: str
    task_id: int
    task_name: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    total_duration: Optional[str]
    executor: Dict[str, Any]
    device: Dict[str, Any]
    summary: ReportSummary
    results: List[ReportResult]


class ExportFormat(str, Enum):
    JSON = "json"
    PDF = "pdf"
    EXCEL = "excel"
    HTML = "html"
    MARKDOWN = "markdown"
    WORD = "word"


# ========== 基线知识库 ==========

class FailurePatternCreate(BaseModel):
    name: str = Field(..., max_length=100)
    category: str = Field(..., max_length=50)
    pattern: str = Field(..., max_length=500)
    description: Optional[str] = None
    suggested_fix: Optional[str] = None


class FailurePatternUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=50)
    pattern: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    suggested_fix: Optional[str] = None


class BaselineCreate(BaseModel):
    device_model: str = Field(..., max_length=100)
    item_id: int
    metric_name: str = Field(..., max_length=100)
    avg_value: str = Field(..., max_length=50)
    min_value: str = Field(..., max_length=50)
    max_value: str = Field(..., max_length=50)
    sample_count: int = Field(default=1, ge=1)


class BaselineUpdate(BaseModel):
    device_model: Optional[str] = Field(None, max_length=100)
    item_id: Optional[int] = None
    metric_name: Optional[str] = Field(None, max_length=100)
    avg_value: Optional[str] = Field(None, max_length=50)
    min_value: Optional[str] = Field(None, max_length=50)
    max_value: Optional[str] = Field(None, max_length=50)
    sample_count: Optional[int] = Field(None, ge=1)


class GoldenCaseCreate(BaseModel):
    item_id: int
    device_model: str = Field(..., max_length=100)
    expected_status: str = Field(default="pass", max_length=20)
    expected_output_pattern: Optional[str] = Field(None, max_length=500)
    sample_output: Optional[str] = None
    is_active: bool = True


class GoldenCaseUpdate(BaseModel):
    item_id: Optional[int] = None
    device_model: Optional[str] = Field(None, max_length=100)
    expected_status: Optional[str] = Field(None, max_length=20)
    expected_output_pattern: Optional[str] = Field(None, max_length=500)
    sample_output: Optional[str] = None
    is_active: Optional[bool] = None


# ========== 测试知识库 ==========

class KnowledgeEntryType(str, Enum):
    DOCUMENT = "document"
    TEST_CASE = "test_case"
    DEVICE_PROFILE = "device_profile"
    RULE = "rule"
    FAILURE_PATTERN = "failure_pattern"
    BASELINE = "baseline"
    SKILL = "skill"


class KnowledgeEntryStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class KnowledgeEntryCreate(BaseModel):
    title: str = Field(..., max_length=200)
    entry_type: KnowledgeEntryType = KnowledgeEntryType.DOCUMENT
    category: Optional[str] = Field(None, max_length=100)
    tags: List[str] = Field(default_factory=list)
    content: Optional[str] = None
    source_type: str = "manual"
    source_file: Optional[str] = Field(None, max_length=500)
    status: KnowledgeEntryStatus = KnowledgeEntryStatus.DRAFT
    meta: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeEntryUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    entry_type: Optional[KnowledgeEntryType] = None
    category: Optional[str] = Field(None, max_length=100)
    tags: Optional[List[str]] = None
    content: Optional[str] = None
    source_type: Optional[str] = None
    source_file: Optional[str] = Field(None, max_length=500)
    status: Optional[KnowledgeEntryStatus] = None
    meta: Optional[Dict[str, Any]] = None


class KnowledgeEntryResponse(BaseModel):
    id: int
    title: str
    entry_type: str
    category: Optional[str]
    tags: List[str]
    content: Optional[str]
    source_type: str
    source_file: Optional[str]
    status: str
    meta: Dict[str, Any]
    embedding: Optional[List[float]]
    pass_count: int
    fail_count: int
    hit_count: int
    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeEntryList(BaseModel):
    items: List[KnowledgeEntryResponse]
    total: int


# ========== 知识库转换 ==========

class KnowledgeConvertTargetType(str, Enum):
    TEST_ITEM = "test_item"
    FAILURE_PATTERN = "failure_pattern"
    BASELINE = "baseline"
    RULE = "rule"


class KnowledgeConvertPreviewRequest(BaseModel):
    target_type: KnowledgeConvertTargetType
    extra_hint: Optional[str] = None


class KnowledgeConvertRequest(BaseModel):
    target_type: KnowledgeConvertTargetType
    preview_data: Dict[str, Any]


class KnowledgeConvertPreviewResponse(BaseModel):
    target_type: str
    preview_data: Dict[str, Any]
    has_llm: bool


class KnowledgeConvertResponse(BaseModel):
    asset_type: str
    detail: Dict[str, Any]


# ========== 通用响应 ==========

class ResponseModel(BaseModel):
    code: int = 200
    message: str = "success"
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    code: int
    message: str
    errors: Optional[Dict[str, List[str]]] = None


# ========== 分页请求 ==========

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
