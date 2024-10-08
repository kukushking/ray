import functools
from typing import Optional

import numpy as np

from ray.rllib.core.models.base import Model
from ray.rllib.core.models.configs import (
    CNNTransposeHeadConfig,
    FreeLogStdMLPHeadConfig,
    MLPHeadConfig,
)
from ray.rllib.core.models.specs.checker import SpecCheckingError
from ray.rllib.core.models.specs.specs_base import Spec
from ray.rllib.core.models.specs.specs_base import TensorSpec
from ray.rllib.core.models.torch.base import TorchModel
from ray.rllib.core.models.torch.primitives import TorchCNNTranspose, TorchMLP
from ray.rllib.models.utils import get_initializer_fn
from ray.rllib.utils.annotations import override
from ray.rllib.utils.framework import try_import_torch

torch, nn = try_import_torch()


def auto_fold_unfold_time(input_spec: str):
    """Automatically folds/unfolds the time dimension of a tensor.

    This is useful when calling the model requires a batch dimension only, but the
    input data has a batch- and a time-dimension. This decorator will automatically
    fold the time dimension into the batch dimension before calling the model and
    unfold the batch dimension back into the time dimension after calling the model.

    Args:
        input_spec: The input spec of the model.

    Returns:
        A decorator that automatically folds/unfolds the time_dimension if present.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, input_data, **kwargs):
            if not hasattr(self, input_spec):
                raise ValueError(
                    "The model must have an input_specs attribute to "
                    "automatically fold/unfold the time dimension."
                )
            if not torch.is_tensor(input_data):
                raise ValueError(
                    f"input_data must be a torch.Tensor to fold/unfold "
                    f"time automatically, but got {type(input_data)}."
                )
            # Attempt to fold/unfold the time dimension.
            actual_shape = list(input_data.shape)
            spec = getattr(self, input_spec)

            try:
                # Validate the input data against the input spec to find out it we
                # should attempt to fold/unfold the time dimension.
                spec.validate(input_data)
            except ValueError as original_error:
                # Attempt to fold/unfold the time dimension.
                # Calculate a new shape for the input data.
                b, t = actual_shape[:2]
                other_dims = actual_shape[2:]
                reshaped_b = b * t
                new_shape = tuple([reshaped_b] + other_dims)
                reshaped_inputs = input_data.reshape(new_shape)
                try:
                    spec.validate(reshaped_inputs)
                except ValueError as new_error:
                    raise SpecCheckingError(
                        f"Attempted to call {func} with input data of shape "
                        f"{actual_shape}. RLlib attempts to automatically fold/unfold "
                        f"the time dimension because {actual_shape} does not match the "
                        f"input spec {spec}. In an attempt to fold the time "
                        f"dimensions to possibly fit the input specs of {func}, "
                        f"RLlib has calculated the new shape {new_shape} and "
                        f"reshaped the input data to {reshaped_inputs}. However, "
                        f"the input data still does not match the input spec. "
                        f"\nOriginal error: \n{original_error}. \nNew error:"
                        f" \n{new_error}."
                    )
                # Call the actual wrapped function
                outputs = func(self, reshaped_inputs, **kwargs)
                # Attempt to unfold the time dimension.
                return outputs.reshape((b, t) + tuple(outputs.shape[1:]))
            # If above we could validate the spec, we can call the actual wrapped
            # function.
            return func(self, input_data, **kwargs)

        return wrapper

    return decorator


class TorchMLPHead(TorchModel):
    def __init__(self, config: MLPHeadConfig) -> None:
        super().__init__(config)

        self.net = TorchMLP(
            input_dim=config.input_dims[0],
            hidden_layer_dims=config.hidden_layer_dims,
            hidden_layer_activation=config.hidden_layer_activation,
            hidden_layer_use_layernorm=config.hidden_layer_use_layernorm,
            hidden_layer_use_bias=config.hidden_layer_use_bias,
            hidden_layer_weights_initializer=config.hidden_layer_weights_initializer,
            hidden_layer_weights_initializer_config=(
                config.hidden_layer_weights_initializer_config
            ),
            hidden_layer_bias_initializer=config.hidden_layer_bias_initializer,
            hidden_layer_bias_initializer_config=(
                config.hidden_layer_bias_initializer_config
            ),
            output_dim=config.output_layer_dim,
            output_activation=config.output_layer_activation,
            output_use_bias=config.output_layer_use_bias,
            output_weights_initializer=config.output_layer_weights_initializer,
            output_weights_initializer_config=(
                config.output_layer_weights_initializer_config
            ),
            output_bias_initializer=config.output_layer_bias_initializer,
            output_bias_initializer_config=config.output_layer_bias_initializer_config,
        )
        # If log standard deviations should be clipped. This should be only true for
        # policy heads. Value heads should never be clipped.
        self.clip_log_std = config.clip_log_std
        # The clipping parameter for the log standard deviation.
        self.log_std_clip_param = torch.Tensor([config.log_std_clip_param])
        # Register a buffer to handle device mapping.
        self.register_buffer("log_std_clip_param_const", self.log_std_clip_param)

    @override(Model)
    def get_input_specs(self) -> Optional[Spec]:
        return TensorSpec("b, d", d=self.config.input_dims[0], framework="torch")

    @override(Model)
    def get_output_specs(self) -> Optional[Spec]:
        return TensorSpec("b, d", d=self.config.output_dims[0], framework="torch")

    @override(Model)
    @auto_fold_unfold_time("input_specs")
    def _forward(self, inputs: torch.Tensor, **kwargs) -> torch.Tensor:
        # Only clip the log standard deviations, if the user wants to clip. This
        # avoids also clipping value heads.
        if self.clip_log_std:
            # Forward pass.
            means, log_stds = torch.chunk(self.net(inputs), chunks=2, dim=-1)
            # Clip the log standard deviations.
            log_stds = torch.clamp(
                log_stds, -self.log_std_clip_param_const, self.log_std_clip_param_const
            )
            return torch.cat((means, log_stds), dim=-1)
        # Otherwise just return the logits.
        else:
            return self.net(inputs)


class TorchFreeLogStdMLPHead(TorchModel):
    """An MLPHead that implements floating log stds for Gaussian distributions."""

    def __init__(self, config: FreeLogStdMLPHeadConfig) -> None:
        super().__init__(config)

        assert config.output_dims[0] % 2 == 0, "output_dims must be even for free std!"
        self._half_output_dim = config.output_dims[0] // 2

        self.net = TorchMLP(
            input_dim=config.input_dims[0],
            hidden_layer_dims=config.hidden_layer_dims,
            hidden_layer_activation=config.hidden_layer_activation,
            hidden_layer_use_layernorm=config.hidden_layer_use_layernorm,
            hidden_layer_use_bias=config.hidden_layer_use_bias,
            hidden_layer_weights_initializer=config.hidden_layer_weights_initializer,
            hidden_layer_weights_initializer_config=(
                config.hidden_layer_weights_initializer_config
            ),
            hidden_layer_bias_initializer=config.hidden_layer_bias_initializer,
            hidden_layer_bias_initializer_config=(
                config.hidden_layer_bias_initializer_config
            ),
            output_dim=self._half_output_dim,
            output_activation=config.output_layer_activation,
            output_use_bias=config.output_layer_use_bias,
            output_weights_initializer=config.output_layer_weights_initializer,
            output_weights_initializer_config=(
                config.output_layer_weights_initializer_config
            ),
            output_bias_initializer=config.output_layer_bias_initializer,
            output_bias_initializer_config=config.output_layer_bias_initializer_config,
        )

        self.log_std = torch.nn.Parameter(
            torch.as_tensor([0.0] * self._half_output_dim)
        )
        # If log standard deviations should be clipped. This should be only true for
        # policy heads. Value heads should never be clipped.
        self.clip_log_std = config.clip_log_std
        # The clipping parameter for the log standard deviation.
        self.log_std_clip_param = torch.Tensor(
            [config.log_std_clip_param], device=self.log_std.device
        )
        # Register a buffer to handle device mapping.
        self.register_buffer("log_std_clip_param_const", self.log_std_clip_param)

    @override(Model)
    def get_input_specs(self) -> Optional[Spec]:
        return TensorSpec("b, d", d=self.config.input_dims[0], framework="torch")

    @override(Model)
    def get_output_specs(self) -> Optional[Spec]:
        return TensorSpec("b, d", d=self.config.output_dims[0], framework="torch")

    @override(Model)
    @auto_fold_unfold_time("input_specs")
    def _forward(self, inputs: torch.Tensor, **kwargs) -> torch.Tensor:
        # Compute the mean first, then append the log_std.
        mean = self.net(inputs)

        # If log standard deviation should be clipped.
        if self.clip_log_std:
            # Clip the log standard deviation to avoid running into too small
            # deviations that factually collapses the policy.
            log_std = torch.clamp(
                self.log_std,
                -self.log_std_clip_param_const,
                self.log_std_clip_param_const,
            )
        else:
            log_std = self.log_std

        return torch.cat([mean, log_std.unsqueeze(0).repeat([len(mean), 1])], axis=1)


class TorchCNNTransposeHead(TorchModel):
    def __init__(self, config: CNNTransposeHeadConfig) -> None:
        super().__init__(config)

        # Initial, inactivated Dense layer (always w/ bias).
        # This layer is responsible for getting the incoming tensor into a proper
        # initial image shape (w x h x filters) for the suceeding Conv2DTranspose stack.
        self.initial_dense = nn.Linear(
            in_features=config.input_dims[0],
            out_features=int(np.prod(config.initial_image_dims)),
            bias=True,
        )

        # Initial Dense layer initializers.
        initial_dense_weights_initializer = get_initializer_fn(
            config.initial_dense_weights_initializer, framework="torch"
        )
        initial_dense_bias_initializer = get_initializer_fn(
            config.initial_dense_bias_initializer, framework="torch"
        )

        # Initialize dense layer weights, if necessary.
        if initial_dense_weights_initializer:
            initial_dense_weights_initializer(
                self.initial_dense.weight,
                **config.initial_dense_weights_initializer_config or {},
            )
        # Initialized dense layer bais, if necessary.
        if initial_dense_bias_initializer:
            initial_dense_bias_initializer(
                self.initial_dense.bias,
                **config.initial_dense_bias_initializer_config or {},
            )

        # The main CNNTranspose stack.
        self.cnn_transpose_net = TorchCNNTranspose(
            input_dims=config.initial_image_dims,
            cnn_transpose_filter_specifiers=config.cnn_transpose_filter_specifiers,
            cnn_transpose_activation=config.cnn_transpose_activation,
            cnn_transpose_use_layernorm=config.cnn_transpose_use_layernorm,
            cnn_transpose_use_bias=config.cnn_transpose_use_bias,
            cnn_transpose_kernel_initializer=config.cnn_transpose_kernel_initializer,
            cnn_transpose_kernel_initializer_config=(
                config.cnn_transpose_kernel_initializer_config
            ),
            cnn_transpose_bias_initializer=config.cnn_transpose_bias_initializer,
            cnn_transpose_bias_initializer_config=(
                config.cnn_transpose_bias_initializer_config
            ),
        )

    @override(Model)
    def get_input_specs(self) -> Optional[Spec]:
        return TensorSpec("b, d", d=self.config.input_dims[0], framework="torch")

    @override(Model)
    def get_output_specs(self) -> Optional[Spec]:
        return TensorSpec(
            "b, w, h, c",
            w=self.config.output_dims[0],
            h=self.config.output_dims[1],
            c=self.config.output_dims[2],
            framework="torch",
        )

    @override(Model)
    @auto_fold_unfold_time("input_specs")
    def _forward(self, inputs: torch.Tensor, **kwargs) -> torch.Tensor:
        out = self.initial_dense(inputs)
        # Reshape to initial 3D (image-like) format to enter CNN transpose stack.
        out = out.reshape((-1,) + tuple(self.config.initial_image_dims))
        out = self.cnn_transpose_net(out)
        # Add 0.5 to center (always non-activated, non-normalized) outputs more
        # around 0.0.
        return out + 0.5
