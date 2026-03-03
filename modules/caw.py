# modules/caw.py
# Crow responses for anyone who dares to CAW or !caw
import re
import random
import time
from typing import Any, List, Pattern
from .base import SimpleCommandModule


def setup(bot: Any) -> 'Caw':
    return Caw(bot)


class Caw(SimpleCommandModule):
    name = "caw"
    version = "1.0.0"
    description = "Responds to CAW or !caw with corvid wisdom and chaos."

    CROW_RESPONSES: List[str] = [
        "CAW! The murder acknowledges your presence, {title}. We are watching.",
        "A crow never forgets a face, {title}. Consider yourself... remembered.",
        "Ah, {title}! Leave something shiny on the windowsill and you'll have a friend for life. Neglect to do so and... well.",
        "The crow does not forget, {title}. The crow does not forgive. The crow will, however, trade you a bottle cap for that sandwich.",
        "CAW CAW CAW, {title}! (That means 'hello' in crow. Probably.)",
        "A murder of crows has assembled, {title}. They have opinions. Many opinions.",
        "The ancient corvids foretold this moment, {title}. Or they just wanted your chips.",
        "One for sorrow, two for joy \u2014 but {title} has summoned a whole murder, which I believe counts as 'chaos'.",
        "Crows can recognize faces and hold grudges for years, {title}. Just thought you should know.",
        "CAW! In crow culture this is considered either rude, a greeting, or a dire warning. The elders disagree.",
        "The crow perches upon the fence post, {title}, and it is judging you. It is always judging you.",
        "A gift of french fries will be accepted, {title}. A gift of vegetables will be remembered. And punished.",
        "The augurs of ancient Rome read omens from corvids, {title}. Right now they're reading: 'chaos incoming'.",
        "CAW CAW, {title}! Your call has been received by the council. Please hold. Current wait time: whenever we feel like it.",
        "Crows have been observed holding funerals for their dead, {title}. They have also been observed stealing shoelaces. Both are entirely true.",
        "The crow knows, {title}. The crow always knows. The crow has been watching since before you arrived.",
        "In Norse mythology, Odin's ravens carried thought and memory across the world. Your crow is carrying... is that a candy wrapper?",
        "CAW! The omen is unclear, {title}. Consult the murder again in three business days.",
        "Crows are among the most intelligent birds on earth, {title}. They are currently using this intelligence to steal your lunch.",
        "The corvid council has convened, {title}. The vote on whether to trust you was: 2 for, 14 against, 1 abstained to steal a shiny button.",
        "CAW-tiously noted, {title}.",
        "Your CAW has been logged, {title}. The crows have been informed. The crows are pleased.",
        "The crow atop the old oak has been there for three days, {title}. It has not moved. It has not blinked. It wants your pretzels.",
        "Beware the crow who brings you gifts, {title} \u2014 for every gift demands a reckoning.",
        "The rookery stirs, {title}. Seven crows rise from the field. Seven is a lot. Seven is too many. Run.",
    ]

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self.set_state("last_response_time", self.get_state("last_response_time", 0.0))
        self.save_state()
        self.RE_CAW: Pattern[str] = re.compile(r'\bCAW\b', re.IGNORECASE)
        self.RE_BANG_CAW: Pattern[str] = re.compile(r'!caw', re.IGNORECASE)

    def _register_commands(self) -> None:
        pass

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if not self.is_enabled(event.target):
            return False

        if self.RE_CAW.search(msg) or self.RE_BANG_CAW.search(msg):
            cooldown = self.get_config_value("cooldown_seconds", event.target, 5.0)
            now = time.time()
            if now - self.get_state("last_response_time", 0.0) >= cooldown:
                self.set_state("last_response_time", now)
                self.save_state()
                title = self.bot.title_for(username)
                response = random.choice(self.CROW_RESPONSES).format(title=title)
                self.safe_reply(connection, event, response)
                return True
        return False
