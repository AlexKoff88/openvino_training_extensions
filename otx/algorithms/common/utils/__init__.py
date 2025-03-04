"""Collection of utils to run common OTX algorithms."""

# Copyright (C) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.

from .callback import (
    InferenceProgressCallback,
    OptimizationProgressCallback,
    TrainingProgressCallback,
)
from .data import get_cls_img_indices, get_image, get_old_new_img_indices
from .utils import UncopiableDefaultDict, get_arg_spec, get_task_class, load_template

__all__ = [
    "get_cls_img_indices",
    "get_old_new_img_indices",
    "TrainingProgressCallback",
    "InferenceProgressCallback",
    "OptimizationProgressCallback",
    "UncopiableDefaultDict",
    "load_template",
    "get_task_class",
    "get_arg_spec",
    "get_image",
]
