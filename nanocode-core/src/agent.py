from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from src.bridge import BridgeBinding, InvalidBridgeSchema, validate_bridge_schema
from src.interpreter import Execution, Interpreter, Program
from src.terms import Term


class Environment(Protocol):
    """Minimal environment protocol for goal-directed Nanocode agents."""

    def reset(self) -> object:
        ...

    def step(self, action: object) -> tuple[object, float, bool, dict]:
        ...


@dataclass(frozen=True)
class Goal:
    name: str
    reward_fn: Callable[[Iterable["EpisodeStep"]], float]
    description: str | None = None


@dataclass(frozen=True)
class AgentPolicy:
    """Pair a Nanocode program with observation/action adapters."""

    program: Program
    encode_observation: Callable[[object], Term] | None = None
    decode_action: Callable[[Term, Execution], object] | None = None
    bridge: BridgeBinding | None = None
    observation_port: str | None = None
    action_port: str | None = None

    def __post_init__(self):
        if self.bridge:
            validate_bridge_schema(self.bridge.schema)
        if self.encode_observation is None and not (self.bridge and self.observation_port):
            raise InvalidBridgeSchema(
                "observation encoding must be provided via encode_observation or a bridge port"
            )
        if self.decode_action is None and not (self.bridge and self.action_port):
            raise InvalidBridgeSchema(
                "action decoding must be provided via decode_action or a bridge port"
            )


@dataclass
class EpisodeStep:
    observation: object
    action: object
    reward: float
    done: bool
    execution: Execution
    info: dict | None = None


@dataclass
class EpisodeResult:
    steps: list[EpisodeStep]
    total_reward: float
    goal_score: float | None


def rollout_agent(
    policy: AgentPolicy,
    env: Environment,
    *,
    interpreter: Interpreter | None = None,
    run_kwargs: dict | None = None,
    max_steps: int | None = None,
    goal: Goal | None = None,
) -> EpisodeResult:
    """Run a Nanocode policy against an environment episode.

    The policy's program is re-rooted per observation, keeping execution
    deterministic while allowing external sensors/bridges to feed into the
    rewrite substrate. The interpreter is instantiated once to preserve
    configuration across steps.
    """

    interpreter = interpreter or Interpreter()
    run_kwargs = run_kwargs or {}

    observation = env.reset()
    steps: list[EpisodeStep] = []
    total_reward = 0.0
    step_count = 0

    while True:
        encoded = _encode_observation(policy, observation)
        execution = interpreter.run(policy.program.with_root(encoded), **run_kwargs)
        action_term = execution.materialize_root()
        action = _decode_action(policy, action_term, execution)

        next_obs, reward, done, info = env.step(action)
        total_reward += reward
        steps.append(
            EpisodeStep(
                observation=observation,
                action=action,
                reward=reward,
                done=done,
                execution=execution,
                info=info,
            )
        )

        step_count += 1
        if done:
            break
        if max_steps is not None and step_count >= max_steps:
            break

        observation = next_obs

    goal_score = goal.reward_fn(steps) if goal else None
    return EpisodeResult(steps=steps, total_reward=total_reward, goal_score=goal_score)


def _encode_observation(policy: AgentPolicy, observation: object) -> Term:
    if policy.bridge and policy.observation_port:
        return policy.bridge.encode_input(policy.observation_port, observation)
    if policy.encode_observation is None:
        raise InvalidBridgeSchema("no observation encoder available")
    return policy.encode_observation(observation)


def _decode_action(policy: AgentPolicy, action_term: Term, execution: Execution) -> object:
    if policy.bridge and policy.action_port:
        return policy.bridge.decode_output(policy.action_port, action_term)
    if policy.decode_action is None:
        raise InvalidBridgeSchema("no action decoder available")
    return policy.decode_action(action_term, execution)

