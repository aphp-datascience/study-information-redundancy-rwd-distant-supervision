import torch

from .helpers.attr import get_deep_attr, set_deep_attr


class ScheduledOptimizer(torch.optim.Optimizer):
    def __init__(self, optim):
        self.optim = optim
        for group in self.optim.param_groups:
            if "schedules" in group:
                if not isinstance(group["schedules"], list):
                    group["schedules"] = [group["schedules"]]
                group["schedules"] = list(group["schedules"])
                for schedule in group["schedules"]:
                    schedule.step(group)
        self.defaults = self.optim.defaults

    def zero_grad(self):
        return self.optim.zero_grad()

    @property
    def param_groups(self):
        return self.optim.param_groups

    @param_groups.setter
    def param_groups(self, value):
        self.optim.param_groups = value

    @property
    def state(self):
        return self.optim.state

    @state.setter
    def state(self, value):
        self.optim.state = value

    def state_dict(self):
        state = {
            "optim": self.optim.state_dict(),
            "lr": [group.get("lr") for group in self.optim.param_groups],
            "schedules": [
                [schedule.state_dict() for schedule in group.get("schedules")]
                for group in self.optim.param_groups
            ],
        }
        for group in state["optim"]["param_groups"]:
            del group["schedules"]
        return state

    def load_state_dict(self, state):
        optim_schedules = [group["schedules"] for group in self.optim.param_groups]
        self.optim.load_state_dict(state["optim"])
        for group, group_schedule, group_schedules_state, lr in zip(
            self.optim.param_groups, optim_schedules, state["schedules"], state["lr"]
        ):
            group["schedules"] = group_schedule
            for schedule, schedule_state in zip(
                group["schedules"], group_schedules_state
            ):
                schedule.load_state_dict(schedule_state)
            group["lr"] = lr

    def step(self, closure=None):
        self.optim.step(closure=closure)
        for group in self.optim.param_groups:
            if "schedules" in group:
                for schedule in group["schedules"]:
                    schedule.step(group)


class LinearSchedule:
    def __init__(
        self,
        total_steps,
        max_value=None,
        start_value=0.0,
        path="lr",
        warmup=True,
        warmup_rate=0.1,
    ):
        self.path = path
        self.start_value = start_value
        self.max_value = max_value
        self.warmup = warmup
        self.warmup_rate = warmup_rate
        self.total_steps = total_steps
        self.idx = 0

    def state_dict(self):
        return {
            "idx": self.idx,
        }

    def load_state_dict(self, state):
        self.idx = state["idx"]

    def step(self, group, closure=None):
        if self.max_value is None:
            self.max_value = get_deep_attr(group, self.path)
        warmup_steps = self.total_steps * self.warmup_rate
        if self.idx < warmup_steps:
            progress = self.idx / warmup_steps
            value = self.start_value + (self.max_value - self.start_value) * progress
        else:
            progress = (self.idx - warmup_steps) / (self.total_steps - warmup_steps)
            value = self.max_value + (0 - self.max_value) * progress
        self.idx += 1
        set_deep_attr(group, self.path, value)


class CyclicalLinearSchedule:
    def __init__(
        self,
        steps_per_epoch: int,
        # total_steps,
        max_value=0.01,
        min_value=0.001,
        epochs_per_cycle=10,
        path="lr",
    ):
        self.path = path
        self.max_value = max_value
        self.min_value = min_value
        self.epochs_per_cycle = epochs_per_cycle
        self.steps_per_epoch = steps_per_epoch
        self.num_epoch = 0
        self.idx = 0

    def state_dict(self):
        return {
            "idx": self.idx,
        }

    def load_state_dict(self, state):
        self.idx = state["idx"]

    def step(self, group, closure=None):
        if self.max_value is None:
            self.max_value = get_deep_attr(group, self.path)

        # progress = (self.num_epoch % self.epochs_per_cycle) / float(
        #     self.epochs_per_cycle
        # )
        # value = (1 - progress) * self.max_value + progress * self.min_value

        value = self.max_value - (
            (self.max_value - self.min_value) / (self.epochs_per_cycle - 1)
        ) * (self.num_epoch % self.epochs_per_cycle)

        if self.idx > (self.num_epoch + 1) * self.steps_per_epoch:
            self.num_epoch += 1
            print("NUM EPOCH:", self.num_epoch)

        self.idx += 1
        set_deep_attr(group, self.path, value)
