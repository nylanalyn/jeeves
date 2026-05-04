from jeeves import Jeeves
from modules.admin_validator import AdminValidator, create_admin_validator
from modules.config_manager import ConfigManager


def test_debug_redaction_hides_super_admin_password_command():
    bot = Jeeves.__new__(Jeeves)

    redacted = bot._redact_sensitive_data("PRIVMSG from Alice: !pass hunter2")

    assert "hunter2" not in redacted
    assert redacted == "PRIVMSG from Alice: !pass [REDACTED]"


def test_debug_redaction_hides_comma_pass_alias():
    bot = Jeeves.__new__(Jeeves)

    redacted = bot._redact_sensitive_data("PUBMSG from Alice in #bots: ,pass hunter2")

    assert "hunter2" not in redacted
    assert redacted.endswith(",pass [REDACTED]")


def test_config_manager_reads_modern_sections():
    manager = ConfigManager({
        "core": {"admins": ["Alice"]},
        "connection": {"server": "irc.example.test"},
        "weather": {"allowed_channels": ["#bots"]},
    })

    assert manager.get_admin_users() == ["Alice"]
    assert manager.get_connection_config()["server"] == "irc.example.test"
    assert manager.get_irc_config()["server"] == "irc.example.test"
    assert manager.get_module_config("weather") == {"allowed_channels": ["#bots"]}


def test_config_manager_keeps_legacy_fallbacks():
    manager = ConfigManager({
        "irc": {"admins": ["LegacyAdmin"], "server": "legacy.example.test"},
        "modules": {"weather": {"enabled": True}},
    })

    assert manager.get_admin_users() == ["LegacyAdmin"]
    assert manager.get_irc_config()["server"] == "legacy.example.test"
    assert manager.get_module_config("weather") == {"enabled": True}


def test_admin_validator_accepts_modern_core_admins_and_sources():
    validator = create_admin_validator(config={"core": {"admins": ["Alice"]}})

    assert validator.is_admin("alice!user@example.test")
    assert not validator.is_admin("bob!user@example.test")


def test_admin_validator_can_delegate_to_bot():
    class BotStub:
        def is_admin(self, source):
            return source == "Alice!user@example.test"

    validator = AdminValidator(bot=BotStub())

    assert validator.is_admin("Alice!user@example.test")
    assert not validator.is_admin("Alice")
