"""003_device_version: additive 设备乐观并发版本列（V1-01 设备改派契约 §2/§6）。

- additive：仅对 devices 表新增 `version INTEGER NOT NULL DEFAULT 1`，不改任何历史
  表结构/数据；既有行自动获得 version=1。
- downgrade：仅移除本 revision 引入的列，历史业务表（users/test_tasks/test_records
  等）的行数据完整保留。
- 采用原生 `ALTER TABLE ... ADD/DROP COLUMN`（SQLite 3.35+ / PostgreSQL 均支持），
  **不做 batch 影子表重建**：devices 被 test_tasks.device_id 外键引用，batch 重建
  （DROP TABLE devices + 复制）在外键强制（PRAGMA foreign_keys=ON，T-02）下会触发
  FOREIGN KEY constraint failed；原生 ADD/DROP COLUMN 不触碰引用方与行数据，最安全。
- 对应 app.models.Device.version（default=1, server_default="1"），由
  scripts/verify_migrations.py 的 DDL 指纹比对自动核验。
"""
from alembic import op


revision = '003_device_version'
down_revision = '002_idempotency'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 原生 ADD COLUMN：既有行自动填充 1，无需重建表，不触发外键检查。
    # DEFAULT '1'（带引号）与 app.models.Device.version 的 server_default="1"
    # 在 SQLAlchemy 结构指纹中一致（都为 '1'）。
    op.execute("ALTER TABLE devices ADD COLUMN version INTEGER NOT NULL DEFAULT '1'")


def downgrade() -> None:
    # 数据保护 + 外键安全：原生 DROP COLUMN，仅移除 version 列，行数据完整保留，
    # 不重建 devices 表（避免 devices 被 test_tasks 外键引用时的 FK 失败）。
    op.execute("ALTER TABLE devices DROP COLUMN version")
