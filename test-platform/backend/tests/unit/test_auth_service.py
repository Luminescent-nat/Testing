"""认证服务单元测试。"""
import pytest
from datetime import timedelta

from app.services.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_token,
)


def test_password_hash_and_verify():
    """密码哈希与验证。"""
    password = "secure_password_123"
    hashed = get_password_hash(password)
    assert verify_password(password, hashed) is True
    assert verify_password("wrong_password", hashed) is False


def test_password_hash_is_different_each_time():
    """相同密码两次哈希结果应不同（盐值不同）。"""
    password = "same_password"
    hash1 = get_password_hash(password)
    hash2 = get_password_hash(password)
    assert hash1 != hash2
    assert verify_password(password, hash1)
    assert verify_password(password, hash2)


def test_long_password_truncation():
    """超过 72 字节的密码应被截断处理。"""
    long_password = "a" * 100
    hashed = get_password_hash(long_password)
    assert verify_password(long_password, hashed) is True


def test_create_and_decode_token():
    """创建并解码 JWT token。"""
    token, expire = create_access_token(data={"sub": "testuser"})
    payload = decode_token(token)
    assert payload is not None
    assert payload.get("sub") == "testuser"
    assert "exp" in payload


def test_decode_expired_token():
    """过期 token 解码返回 None。"""
    token, _ = create_access_token(
        data={"sub": "testuser"},
        expires_delta=timedelta(seconds=-1),
    )
    assert decode_token(token) is None


def test_decode_invalid_token():
    """非法 token 解码返回 None。"""
    assert decode_token("not.a.token") is None
