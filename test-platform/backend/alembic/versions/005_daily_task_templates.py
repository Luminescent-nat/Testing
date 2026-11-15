"""005_daily_task_templates: daily 模板/实例字段 + 计划时刻唯一索引（R16/R17/R20）。

- additive：对 test_tasks 新增 task_kind/template_id/scheduled_for/
  item_snapshot/item_snapshot_status 五列，不改历史表结构与数据；
  既有行 task_kind 默认 'instance'（视为普通执行实例），无快照视为 legacy。
- 唯一约束 UNIQUE(template_id, scheduled_for) 用原生 CREATE UNIQUE INDEX 实现
  （SQLite 下 ALTER TABLE 无法追加表级约束，且 004 已证 batch 影子表重建会被
  test_records 外键引用触发 FK 失败；唯一索引对 NULL 行的 SQL 标准语义正好
  满足「template_id 非 null 时同一计划时刻至多一个实例」）。
- 模型侧用同等义的 Index(..., unique=True)（app/models/__init__.py），
  保证 scripts/verify_migrations.py 的 DDL 指纹（indexes/uniques）与模型一致。
- downgrade 先删索引再删列，顺序安全。
"""
from alembic import op
import sqlalchemy as sa


revision = '005_daily_task_templates'
down_revision = '004_task_deleted_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 原生 ADD COLUMN：既有行默认值/NULL，无需重建表，不触发外键检查（同 004）。
    # server_default 与 app.models 对齐（DDL 指纹 default 一致）；
    # template_id 带自引用外键（与模型 ForeignKey 指纹一致）。
    op.execute(
        "ALTER TABLE test_tasks ADD COLUMN task_kind VARCHAR(20) NOT NULL DEFAULT 'instance'"
    )
    op.execute(
        "ALTER TABLE test_tasks ADD COLUMN template_id INTEGER NULL "
        "REFERENCES test_tasks (id)"
    )
    op.execute("ALTER TABLE test_tasks ADD COLUMN scheduled_for DATETIME NULL")
    op.execute("ALTER TABLE test_tasks ADD COLUMN item_snapshot JSON NULL")
    op.execute("ALTER TABLE test_tasks ADD COLUMN item_snapshot_status VARCHAR(20) NULL")

    # 计划时刻唯一索引：同一模板同一 scheduled_for 至多一个实例（调度并发幂等）。
    op.create_index(
        'uq_task_template_scheduled_for',
        'test_tasks',
        ['template_id', 'scheduled_for'],
        unique=True,
    )
    # 列表按 task_kind 过滤的性能索引
    op.create_index('ix_test_tasks_task_kind', 'test_tasks', ['task_kind'])


def downgrade() -> None:
    op.drop_index('ix_test_tasks_task_kind', table_name='test_tasks')
    op.drop_index('uq_task_template_scheduled_for', table_name='test_tasks')
    op.execute("ALTER TABLE test_tasks DROP COLUMN item_snapshot_status")
    op.execute("ALTER TABLE test_tasks DROP COLUMN item_snapshot")
    op.execute("ALTER TABLE test_tasks DROP COLUMN scheduled_for")
    op.execute("ALTER TABLE test_tasks DROP COLUMN template_id")
    op.execute("ALTER TABLE test_tasks DROP COLUMN task_kind")
