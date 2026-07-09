"""core/security 단위 테스트 — next 화이트리스트, state/JWT, refresh 해시."""

import uuid

import jwt
import pytest

from app.core.security import (
    InvalidStateError,
    create_access_token,
    create_state_token,
    decode_access_token,
    decode_state_token,
    generate_refresh_token,
    hash_refresh_token,
    sanitize_next_path,
)


class TestSanitizeNextPath:
    @pytest.mark.parametrize("path", ["/", "/mypage", "/onboarding?step=2", "/a/b/c"])
    def test_valid_relative_paths(self, path):
        assert sanitize_next_path(path) == path

    @pytest.mark.parametrize(
        "path",
        [
            "https://evil.com",
            "http://evil.com/",
            "//evil.com",
            "/\\evil",
            "relative-no-slash",
            "",
            "/ok\r\nSet-Cookie: x=1",  # 제어문자 (헤더 인젝션)
            "/redirect?to=https://ok.com" + "\\",
        ],
    )
    def test_invalid_paths_fall_back_to_root(self, path):
        assert sanitize_next_path(path) == "/"


class TestStateToken:
    def test_roundtrip(self):
        state = create_state_token("kakao", "/mypage")
        assert decode_state_token(state, "kakao") == "/mypage"

    def test_provider_mismatch(self):
        state = create_state_token("kakao", "/")
        with pytest.raises(InvalidStateError):
            decode_state_token(state, "google")

    def test_garbage_token(self):
        with pytest.raises(InvalidStateError):
            decode_state_token("garbage", "kakao")

    def test_access_token_is_not_valid_state(self):
        # purpose 클레임 불일치 — access JWT 를 state 로 재사용 불가
        token = create_access_token(uuid.uuid4())
        with pytest.raises(InvalidStateError):
            decode_state_token(token, "kakao")

    def test_state_next_is_sanitized_on_decode(self):
        # state 내 next 가 어떤 경로여도 디코드 시 재검증
        bad = jwt.encode(
            {
                "purpose": "oauth_state",
                "provider": "kakao",
                "next": "https://evil.com",
                "exp": 9999999999,
            },
            "test-jwt-secret",
            algorithm="HS256",
        )
        assert decode_state_token(bad, "kakao") == "/"


class TestAccessToken:
    def test_roundtrip_claims(self):
        user_id = uuid.uuid4()
        claims = decode_access_token(create_access_token(user_id))
        assert claims["sub"] == str(user_id)
        assert "exp" in claims and "iat" in claims and "jti" in claims

    def test_wrong_signature_rejected(self):
        token = jwt.encode({"sub": "x"}, "other-secret", algorithm="HS256")
        with pytest.raises(jwt.PyJWTError):
            decode_access_token(token)


class TestRefreshToken:
    def test_generate_is_random_and_opaque(self):
        t1, t2 = generate_refresh_token(), generate_refresh_token()
        assert t1 != t2
        assert len(t1) >= 40  # 256bit urlsafe

    def test_hash_is_sha256_hex(self):
        h = hash_refresh_token("abc")
        assert len(h) == 64
        assert h == hash_refresh_token("abc")  # 결정적
        assert h != hash_refresh_token("abd")
