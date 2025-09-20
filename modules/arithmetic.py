# modules/arithmetic.py
# A module for performing calculations, with a butler's occasional whimsy.
import re
import random
import operator
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Arithmetic(bot, config)

class Arithmetic(SimpleCommandModule):
    name = "arithmetic"
    version = "1.1.0" # version bumped for refactor
    description = "Performs calculations with configurable reliability."

    def __init__(self, bot, config):
        super().__init__(bot)
        self.RELIABILITY_PERCENT = config.get("reliability_percent", 85)
        self.MAX_FUDGE_FACTOR = config.get("max_fudge_factor", 2)
        
        self.set_state("calculations_performed", self.get_state("calculations_performed", 0))
        self.set_state("whimsical_results", self.get_state("whimsical_results", 0))
        self.save_state()
        
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        # This regex will look for "what is/what's" followed by a math expression.
        self.RE_NATURAL_CALC = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:what'?s|what\s+is)\s+([0-9\s\+\-\*/\^\.\(\)]+)\??",
            re.IGNORECASE
        )

    def _register_commands(self):
        self.register_command(r"^\s*!calc\s+(.+)$", self._cmd_calc,
                              name="calc", description="Calculate a mathematical expression.")
        self.register_command(r"^\s*!arithmetic\s+stats\s*$", self._cmd_stats,
                              name="arithmetic stats", admin_only=True, description="Show calculation statistics.")

    def on_ambient_message(self, connection, event, msg, username):
        match = self.RE_NATURAL_CALC.search(msg)
        if match:
            expression = match.group(1).strip()
            self._handle_calculation(connection, event, username, expression)
            return True
            
        return False

    def _cmd_calc(self, connection, event, msg, username, match):
        expression = match.group(1).strip()
        self._handle_calculation(connection, event, username, expression)
        return True

    def _handle_calculation(self, connection, event, username, expression):
        try:
            result = self._safe_eval(expression)
            is_reliable = random.randint(1, 100) <= self.RELIABILITY_PERCENT
            
            self.set_state("calculations_performed", self.get_state("calculations_performed", 0) + 1)

            if is_reliable:
                response = f"If my calculations are correct, {self.bot.title_for(username)}, the answer is {result}."
            else:
                fudge = random.uniform(-self.MAX_FUDGE_FACTOR, self.MAX_FUDGE_FACTOR)
                
                # Make the fudge more "natural" - integers for integer results
                if isinstance(result, int):
                    whimsical_result = result + int(fudge)
                else:
                    whimsical_result = result + fudge
                
                response = f"I believe the figure is approximately {whimsical_result:.2f}, {self.bot.title_for(username)}."
                self.set_state("whimsical_results", self.get_state("whimsical_results", 0) + 1)
            
            self.save_state()
            self.safe_reply(connection, event, response)
        
        except (ValueError, ZeroDivisionError) as e:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I encountered an issue: {e}")
        except Exception:
            self.safe_reply(connection, event, f"I'm afraid that calculation is beyond my station, {self.bot.title_for(username)}.")

    def _safe_eval(self, expr):
        """A simple, safe evaluator for basic arithmetic, now with DoS protection."""
        if len(expr) > 100:
            raise ValueError("Expression is too long for my abacus.")
        if expr.count('**') > 2 and expr.count('^') > 2:
            raise ValueError("Such exponentiation is beyond my humble abilities.")
            
        expr = expr.replace('^', '**')
        
        # Corrected regex to allow for the possibility of `**` being formed.
        if not re.match(r"^[0-9\s\+\-\*/\.\(\)\^]+$", expr.replace('**', '^')):
            raise ValueError("Invalid characters in expression.")

        return eval(expr, {'__builtins__': {}}, {})

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        total = self.get_state("calculations_performed", 0)
        whimsical = self.get_state("whimsical_results", 0)
        reliability = ((total - whimsical) / total * 100) if total > 0 else 100
        
        self.safe_reply(connection, event, 
            f"Arithmetic stats: {total} calculations performed. "
            f"{whimsical} results were... whimsical. "
            f"Observed reliability: {reliability:.1f}%."
        )
        return True

