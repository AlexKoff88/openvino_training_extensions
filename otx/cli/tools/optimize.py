"""Model optimization tool."""

# Copyright (C) 2021 Intel Corporation
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

import json

from otx.api.entities.inference_parameters import InferenceParameters
from otx.api.entities.model import ModelEntity
from otx.api.entities.optimization_parameters import OptimizationParameters
from otx.api.entities.resultset import ResultSetEntity
from otx.api.entities.subset import Subset
from otx.api.entities.task_environment import TaskEnvironment
from otx.api.usecases.tasks.interfaces.optimization_interface import OptimizationType
from otx.cli.manager import ConfigManager
from otx.cli.utils.importing import get_impl_class
from otx.cli.utils.io import read_model, save_model_data
from otx.cli.utils.parser import (
    add_hyper_parameters_sub_parser,
    get_parser_and_hprams_data,
)
from otx.core.data.adapter import get_dataset_adapter

# pylint: disable=too-many-locals


def get_args():
    """Parses command line arguments.

    It dynamically generates help for hyper-parameters which are specific to particular model template.
    """
    parser, hyper_parameters, params = get_parser_and_hprams_data()

    parser.add_argument(
        "--train-data-roots",
        help="Comma-separated paths to training data folders.",
    )
    parser.add_argument(
        "--val-data-roots",
        help="Comma-separated paths to validation data folders.",
    )
    parser.add_argument(
        "--load-weights",
        help="Load weights of trained model",
    )
    parser.add_argument(
        "--save-model-to",
        help="Location where trained model will be stored.",
    )
    parser.add_argument(
        "--save-performance",
        help="Path to a json file where computed performance will be stored.",
    )
    parser.add_argument(
        "--work-dir",
        help="Location where the intermediate output of the task will be stored.",
        default=None,
    )

    add_hyper_parameters_sub_parser(parser, hyper_parameters)
    override_param = [f"params.{param[2:].split('=')[0]}" for param in params if param.startswith("--")]

    return parser.parse_args(), override_param


def main():
    """Main function that is used for model training."""

    # Dynamically create an argument parser based on override parameters.
    args, override_param = get_args()

    config_manager = ConfigManager(args, workspace_root=args.work_dir, mode="train")
    # Auto-Configuration for model template
    config_manager.configure_template()

    # The default in the workspace is the model weight of the OTX train.
    if not args.load_weights and config_manager.check_workspace():
        args.load_weights = str(config_manager.workspace_root / "models/weights.pth")

    is_pot = False
    if args.load_weights.endswith(".bin") or args.load_weights.endswith(".xml"):
        is_pot = True

    template = config_manager.template
    if not is_pot and template.entrypoints.nncf is None:
        raise RuntimeError(f"Optimization by NNCF is not available for template {args.template}")

    # Update Hyper Parameter Configs
    hyper_parameters = config_manager.get_hyparams_config(override_param)

    # Get classes for Task, ConfigurableParameters and Dataset.
    task_class = get_impl_class(template.entrypoints.openvino if is_pot else template.entrypoints.nncf)

    # Auto-Configuration for Dataset configuration
    config_manager.configure_data_config(update_data_yaml=config_manager.check_workspace())
    dataset_config = config_manager.get_dataset_config(subsets=["train", "val"])
    dataset_adapter = get_dataset_adapter(**dataset_config)
    dataset, label_schema = dataset_adapter.get_otx_dataset(), dataset_adapter.get_label_schema()

    environment = TaskEnvironment(
        model=None,
        hyper_parameters=hyper_parameters,
        label_schema=label_schema,
        model_template=template,
    )

    environment.model = read_model(environment.get_model_configuration(), args.load_weights, None)

    task = task_class(task_environment=environment)

    output_model = ModelEntity(dataset, environment.get_model_configuration())

    task.optimize(
        OptimizationType.POT if is_pot else OptimizationType.NNCF,
        dataset,
        output_model,
        OptimizationParameters(),
    )

    if "save_model_to" not in args or not args.save_model_to:
        args.save_model_to = str(config_manager.workspace_root / "model-optimized")
    save_model_data(output_model, args.save_model_to)

    validation_dataset = dataset.get_subset(Subset.VALIDATION)
    predicted_validation_dataset = task.infer(
        validation_dataset.with_empty_annotations(),
        InferenceParameters(is_evaluation=True),
    )

    resultset = ResultSetEntity(
        model=output_model,
        ground_truth_dataset=validation_dataset,
        prediction_dataset=predicted_validation_dataset,
    )
    task.evaluate(resultset)
    assert resultset.performance is not None
    print(resultset.performance)

    if args.save_performance:
        with open(args.save_performance, "w", encoding="UTF-8") as write_file:
            json.dump(
                {resultset.performance.score.name: resultset.performance.score.value},
                write_file,
            )

    return dict(retcode=0, template=template.name)


if __name__ == "__main__":
    main()
