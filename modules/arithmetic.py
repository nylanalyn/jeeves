# modules/arithmetic.py
# A module for performing calculations, with a butler's occasional whimsy.
import re
import random
import operator
import ast
from typing import Any, Pattern, Union
from .base import SimpleCommandModule, admin_required

def setup(bot: Any) -> 'Arithmetic':
    return Arithmetic(bot)

class Arithmetic(SimpleCommandModule):
    name = "arithmetic"
    version = "2.0.1" # Added missing is_enabled check
    description = "Performs calculations with configurable reliability."

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self.set_state("calculations_performed", self.get_state("calculations_performed", 0))
        self.set_state("whimsical_results", self.get_state("whimsical_results", 0))
        self.save_state()

        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.RE_NATURAL_CALC: Pattern[str] = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:what'?s|what\s+is)\s+([0-9\s\+\-\*/\^\.\(\)]+)\??",
            re.IGNORECASE
        )

    def _register_commands(self) -> None:
        self.register_command(r"^\s*!calc\s+(.+)$", self._cmd_calc,
                              name="calc", description="Calculate a mathematical expression.")
        self.register_command(r"^\s*!arithmetic\s+stats\s*$", self._cmd_stats,
                              name="arithmetic stats", admin_only=True, description="Show calculation statistics.")

    def on_ambient_message(self, connection: Any, event: Any, msg: str, username: str) -> bool:
        if not self.is_enabled(event.target):
            return False

        match = self.RE_NATURAL_CALC.search(msg)
        if match:
            expression = match.group(1).strip()
            self._handle_calculation(connection, event, username, expression)
            return True

        return False

    def _cmd_calc(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        expression = match.group(1).strip()
        self._handle_calculation(connection, event, username, expression)
        return True

    def _handle_calculation(self, connection: Any, event: Any, username: str, expression: str) -> None:
        try:
            result = self._safe_eval(expression)
            
            # Fetch reliability settings dynamically for the current channel
            reliability_percent = self.get_config_value("reliability_percent", event.target, 85)
            max_fudge_factor = self.get_config_value("max_fudge_factor", event.target, 2)

            is_reliable = random.randint(1, 100) <= reliability_percent
            
            self.set_state("calculations_performed", self.get_state("calculations_performed", 0) + 1)

            if is_reliable:
                response = f"I scribbled the math on the back of a rain-soaked napkin, {self.bot.title_for(username)}, and the answer reads {result}."
            else:
                fudge = random.uniform(-max_fudge_factor, max_fudge_factor)
                
                if isinstance(result, int):
                    whimsical_result = result + int(fudge)
                else:
                    whimsical_result = result + fudge
                
                response = f"The numbers are smeared and the neon keeps flickering, {self.bot.title_for(username)}, but I'd call it {whimsical_result:.2f}."
                self.set_state("whimsical_results", self.get_state("whimsical_results", 0) + 1)
            
            self.save_state()
            self.safe_reply(connection, event, response)
        
        except (ValueError, ZeroDivisionError) as e:
            self.safe_reply(connection, event, f"Ran the figures and hit a brick wall, {self.bot.title_for(username)}: {e}")
        except Exception:
            self.safe_reply(connection, event, f"That calculation is rougher than a back-alley shakedown, {self.bot.title_for(username)}.")

    def _safe_eval(self, expr: str) -> Union[int, float]:
        """A safe evaluator for basic arithmetic using AST parsing."""
        if len(expr) > 100:
            raise ValueError("That expression stretches longer than a midnight stakeout.")

        expr = expr.replace('^', '**')

        if not re.match(r"^[0-9\s\+\-\*/\.\(\)\^]+$", expr.replace('**', '^')):
            raise ValueError("Those characters don't belong on these streets.")

        # Parse the expression into an AST
        try:
            tree = ast.parse(expr, mode='eval')
        except SyntaxError:
            raise ValueError("Can't parse that syntax through the cigarette smoke.")

        # Validate that only safe operations are used
        for node in ast.walk(tree):
            if isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant, ast.Expression)):
                continue
            elif isinstance(node, ast.operator):
                continue
            elif isinstance(node, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd)):
                continue
            else:
                raise ValueError(f"That operation ({node.__class__.__name__}) isn't sanctioned by the department.")

        # Check for excessive nesting/complexity
        if self._ast_depth(tree) > 20:
            raise ValueError("Too many twists in that caper for my ledger.")

        # Evaluate the validated AST
        allowed_operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.Mod: operator.mod,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }

        def eval_node(node):
            if isinstance(node, ast.Constant):  # Python 3.8+
                return node.value
            elif isinstance(node, ast.Num):  # Python 3.7 compatibility
                return node.n
            elif isinstance(node, ast.BinOp):
                left = eval_node(node.left)
                right = eval_node(node.right)
                op = allowed_operators[type(node.op)]
                # Limit exponentiation to prevent DoS
                if isinstance(node.op, ast.Pow) and abs(right) > 100:
                    raise ValueError("That kind of power play blows the precinct fuse box.")
                return op(left, right)
            elif isinstance(node, ast.UnaryOp):
                operand = eval_node(node.operand)
                op = allowed_operators[type(node.op)]
                return op(operand)
            elif isinstance(node, ast.Expression):
                return eval_node(node.body)
            else:
                raise ValueError("That's a trick none of the math boys downtown can pull.")

        return eval_node(tree)

    def _ast_depth(self, node: Any, depth: int = 0) -> int:
        """Calculate the maximum depth of an AST tree."""
        if not isinstance(node, ast.AST):
            return depth
        max_child_depth = depth
        for child in ast.iter_child_nodes(node):
            child_depth = self._ast_depth(child, depth + 1)
            max_child_depth = max(max_child_depth, child_depth)
        return max_child_depth

    @admin_required
    def _cmd_stats(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        total = self.get_state("calculations_performed", 0)
        whimsical = self.get_state("whimsical_results", 0)
        reliability = ((total - whimsical) / total * 100) if total > 0 else 100

        self.safe_reply(connection, event,
            f"Arithmetic stats: {total} calculations performed. "
            f"{whimsical} results were... whimsical. "
            f"Observed reliability: {reliability:.1f}%."
        )
        return True
