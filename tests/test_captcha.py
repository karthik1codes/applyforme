from __future__ import annotations

from applyforme import captcha


def test_captcha_detection_is_manual_only(monkeypatch):
    challenge = captcha.CaptchaChallenge(kind="recaptcha_v2", sitekey="site-key", extra={})
    monkeypatch.setattr(captcha, "detect_captcha", lambda page: challenge)
    monkeypatch.setattr(captcha, "captcha_solved_on_page", lambda page: False)

    messages: list[tuple[str, str]] = []
    ok, note = captcha.resolve_page_captchas(object(), live=lambda phase, text: messages.append((phase, text)))

    assert ok is False
    assert "solve it in the browser" in note
    assert "Automatic/third-party CAPTCHA solving is disabled" in note
    assert messages and messages[0][0] == "captcha"
    # No solver API/secret path exists any more.
    assert not hasattr(captcha, "_solver_enabled")
    assert not hasattr(captcha, "solve_with_2captcha")


def test_captcha_already_satisfied_does_not_block(monkeypatch):
    challenge = captcha.CaptchaChallenge(kind="hcaptcha", sitekey="site-key", extra={})
    monkeypatch.setattr(captcha, "detect_captcha", lambda page: challenge)
    monkeypatch.setattr(captcha, "captcha_solved_on_page", lambda page: True)
    ok, note = captcha.resolve_page_captchas(object())
    assert ok is True
    assert note == "captcha already satisfied"


def test_no_captcha_is_clear():
    class BlankPage:
        def is_closed(self):
            return False

        def evaluate(self, *_args, **_kwargs):
            return None

    ok, note = captcha.resolve_page_captchas(BlankPage())
    assert ok is True
    assert note == "no captcha"
