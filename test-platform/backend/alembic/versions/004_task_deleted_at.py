"""004_task_deleted_at: additive 任务软删除列（契约 task-execution §8 / V1-09b）。

- additive：仅对 test_tasks 表新增 `deleted_at DATETIME NULL`，不改任何历史
  表结构/数据；既有行 deleted_at 为 NULL（视为未删除）。
- 与 app.models.TestTask.deleted_at（nullable=True）一致，供
  scripts/verify_migrations.py 的 DDL 指纹比对自动核验。
- downgrade 数据保护：存在 deleted_at 非空的行（已软删除任务）时拒绝降级，
  防止删除标记丢失导致已删除任务重新出现；无软删除数据时才 DROP COLUMN。
- 采用原生 ALTER TABLE ADD/DROP COLUMN（同 003：test_tasks 被 test_records
  外键引用，batch 影子表重建在 PRAGMA foreign_keys=ON 下会触发 FK 失败）。
"""
from alembic import op
from sqlalchemy import text


revision = '004_task_deleted_at'
down_revision = '003_device_version'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 原生 ADD COLUMN：既有行 deleted_at=NULL，无需重建表，不触发外键检查。
    op.execute("ALTER TABLE test_tasks ADD COLUMN deleted_at DATETIME NULL")


def downgrade() -> None:
    # 数据保护：已软删除（deleted_at 非空）的行一旦丢列，删除标记即丢失，
    # 已删除任务会在列表中重新出现，因此拒绝在有软删除数据时降级。
    bind = op.get_bind()
    deleted_rows = bind.execute(
        text("SELECT COUNT(*) FROM test_tasks WHERE deleted_at IS NOT NULL")
    ).scalar()
    if deleted_rows:
        raise RuntimeError(
            f"无法降级 004_task_deleted_at：存在 {deleted_rows} 行已软删除任务"
            "（deleted_at 非空），降级将丢失删除标记；请先归档/清理软删除数据。"
        )
    op.execute("ALTER TABLE test_tasks DROP COLUMN deleted_at")
