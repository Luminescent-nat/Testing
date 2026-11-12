"""002_idempotency: additive idempotency_records table

Revision ID: 002_idempotency
Revises: 0817df993d8b
Create Date: 2026-11-12

V1-05 迁移闭环要求：
- additive：仅新增 idempotency_records 表，不改任何历史表结构/数据；
- downgrade 只删除该表，users/test_tasks/test_records 等历史表数据必须
  完整保留（revision 级可逆回滚证据，对应设计第 5 节与 RR-T02 遗留项）。

结构必须与 app.models.IdempotencyRecord 完全一致（逐列/索引/唯一约束/
外键，由 scripts/verify_migrations.py 的 DDL 指纹比对自动核验）。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_idempotency'
down_revision = '0817df993d8b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'idempotency_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('operation', sa.String(length=50), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('request_sha256', sa.String(length=64), nullable=False),
        sa.Column('response_json', sa.JSON(), nullable=True),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['task_id'], ['test_tasks.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'operation', 'idempotency_key',
                            name='uq_idempotency_user_op_key'),
    )
    with op.batch_alter_table('idempotency_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_idempotency_records_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_idempotency_records_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_idempotency_records_task_id'), ['task_id'], unique=False)


def downgrade() -> None:
    # 只删除本 revision 引入的表；历史表与其数据完整保留。
    with op.batch_alter_table('idempotency_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_idempotency_records_task_id'))
        batch_op.drop_index(batch_op.f('ix_idempotency_records_user_id'))
        batch_op.drop_index(batch_op.f('ix_idempotency_records_id'))

    op.drop_table('idempotency_records')
