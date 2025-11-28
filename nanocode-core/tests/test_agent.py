from __future__ import annotations

from dataclasses import dataclass

from src.agent import AgentPolicy, Goal, rollout_agent
from src.interpreter import Program
from src.rewrite import Pattern, Rule
from src.terms import Term


@dataclass
class CounterEnv:
    target: int

    def reset(self) -> int:
        self.state = 0
        return self.state

    def step(self, action: str):
        if action == "act_inc":
            self.state += 1
            reward = 1.0
        else:
            reward = 0.0

        done = self.state >= self.target
        return self.state, reward, done, {"state": self.state}


def encode_observation(value: int) -> Term:
    return Term(sym="obs", scale=0, children=[Term(sym=str(value), scale=0)])


def make_policy(target: int) -> AgentPolicy:
    def choose_action(term: Term, store):
        value = int(term.children[0].sym)
        next_sym = "act_inc" if value < target else "act_hold"
        return Term(sym=next_sym, scale=term.scale)

    program = Program(
        name="counter",
        root=encode_observation(0),
        rules=[Rule(name="choose", pattern=Pattern(sym="obs", scale=0), action=choose_action)],
        max_steps=4,
    )

    return AgentPolicy(
        program=program,
        encode_observation=encode_observation,
        decode_action=lambda term, _: term.sym,
    )


def test_rollout_agent_counts_to_target():
    env = CounterEnv(target=3)
    policy = make_policy(target=3)
    result = rollout_agent(policy, env)

    assert result.total_reward == 3.0
    assert [step.action for step in result.steps] == ["act_inc", "act_inc", "act_inc"]
    assert result.steps[-1].done is True
    assert result.goal_score is None


def test_rollout_agent_with_goal_reward():
    env = CounterEnv(target=2)
    policy = make_policy(target=2)

    def goal_reward(steps):
        return sum(step.reward for step in steps) - len(steps) * 0.1

    goal = Goal(name="dense_reward", reward_fn=goal_reward)
    result = rollout_agent(policy, env, goal=goal)

    assert result.goal_score == 1.8  # (1+1) - 2*0.1
    assert len(result.steps) == 2
    assert result.total_reward == 2.0
