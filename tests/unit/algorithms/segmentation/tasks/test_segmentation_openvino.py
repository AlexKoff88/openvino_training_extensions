# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import copy
import os

import numpy as np
import pytest
from openvino.model_zoo.model_api.models import Model

import otx.algorithms.segmentation.tasks.openvino
from otx.algorithms.segmentation.configs.base import SegmentationConfig
from otx.algorithms.segmentation.tasks.openvino import (
    OpenVINOSegmentationInferencer,
    OpenVINOSegmentationTask,
)
from otx.api.configuration.helper import create
from otx.api.entities.annotation import (
    Annotation,
    AnnotationSceneEntity,
    AnnotationSceneKind,
)
from otx.api.entities.datasets import DatasetEntity
from otx.api.entities.label import LabelEntity
from otx.api.entities.metrics import Performance, ScoreMetric
from otx.api.entities.model_template import parse_model_template
from otx.api.entities.resultset import ResultSetEntity
from otx.api.entities.scored_label import ScoredLabel
from otx.api.entities.shapes.polygon import Point, Polygon
from otx.api.usecases.evaluation.metrics_helper import MetricsHelper
from otx.api.usecases.tasks.interfaces.optimization_interface import OptimizationType
from otx.api.utils.shape_factory import ShapeFactory
from tests.test_suite.e2e_test_system import e2e_pytest_unit
from tests.unit.algorithms.segmentation.test_helpers import (
    DEFAULT_SEG_TEMPLATE_DIR,
    generate_otx_dataset,
    generate_otx_label_schema,
    init_environment,
)


class TestOpenVINOSegmentationInferencer:
    @pytest.fixture(autouse=True)
    def setup(self, mocker) -> None:
        model_template = parse_model_template(os.path.join(DEFAULT_SEG_TEMPLATE_DIR, "template.yaml"))
        hyper_parameters = create(model_template.hyper_parameters.data)
        seg_params = SegmentationConfig(header=hyper_parameters.header)
        label_schema = generate_otx_label_schema()
        mocker.patch("otx.algorithms.segmentation.tasks.openvino.OpenvinoAdapter")
        mocker.patch.object(Model, "create_model")
        self.seg_ov_inferencer = OpenVINOSegmentationInferencer(seg_params, label_schema, "")
        self.seg_ov_inferencer.model = mocker.patch("openvino.model_zoo.model_api.models.Model", autospec=True)

        self.fake_input = np.full((5, 1), 0.1)

    @e2e_pytest_unit
    def test_pre_process(self):
        self.seg_ov_inferencer.model.preprocess.return_value = {"foo": "bar"}
        returned_value = self.seg_ov_inferencer.pre_process(self.fake_input)

        assert returned_value == {"foo": "bar"}

    @e2e_pytest_unit
    def test_post_process(self):
        fake_prediction = {"pred": self.fake_input}
        fake_metadata = {"soft_prediction": self.fake_input, "feature_vector": None}
        self.seg_ov_inferencer.model.postprocess.return_value = np.ones((5, 1))
        returned_value = self.seg_ov_inferencer.post_process(fake_prediction, fake_metadata)

        assert len(returned_value) == 3
        assert np.array_equal(returned_value[2], self.fake_input)

    @e2e_pytest_unit
    def test_predict(self, mocker):
        fake_output = AnnotationSceneEntity(kind=AnnotationSceneKind.ANNOTATION, annotations=[])
        mock_pre_process = mocker.patch.object(OpenVINOSegmentationInferencer, "pre_process", return_value=("", ""))
        mock_forward = mocker.patch.object(OpenVINOSegmentationInferencer, "forward")
        mock_post_process = mocker.patch.object(
            OpenVINOSegmentationInferencer, "post_process", return_value=fake_output
        )
        returned_value = self.seg_ov_inferencer.predict(self.fake_input)

        mock_pre_process.assert_called_once()
        mock_forward.assert_called_once()
        mock_post_process.assert_called_once()
        assert returned_value == fake_output

    @e2e_pytest_unit
    def test_forward(self):
        fake_output = {"pred": np.full((5, 1), 0.9)}
        self.seg_ov_inferencer.model.infer_sync.return_value = fake_output
        returned_value = self.seg_ov_inferencer.forward({"image": self.fake_input})

        assert returned_value == fake_output


class TestOpenVINOSegmentationTask:
    @pytest.fixture(autouse=True)
    def setup(self, mocker, otx_model) -> None:
        model_template = parse_model_template(os.path.join(DEFAULT_SEG_TEMPLATE_DIR, "template.yaml"))
        hyper_parameters = create(model_template.hyper_parameters.data)
        label_schema = generate_otx_label_schema()
        task_env = init_environment(hyper_parameters, model_template)
        seg_params = SegmentationConfig(header=hyper_parameters.header)
        mocker.patch("otx.algorithms.segmentation.tasks.openvino.OpenvinoAdapter")
        mocker.patch.object(Model, "create_model")
        seg_ov_inferencer = OpenVINOSegmentationInferencer(seg_params, label_schema, "")

        task_env.model = otx_model
        mocker.patch.object(OpenVINOSegmentationTask, "load_inferencer", return_value=seg_ov_inferencer)
        self.seg_ov_task = OpenVINOSegmentationTask(task_env)

    @e2e_pytest_unit
    def test_infer(self, mocker):
        self.dataset = generate_otx_dataset()
        fake_annotation = [
            Annotation(
                Polygon(points=[Point(0, 0)]),
                id=0,
                labels=[ScoredLabel(LabelEntity(name="fake", domain="SEGMENTATION"), probability=1.0)],
            )
        ]
        fake_ann_scene = AnnotationSceneEntity(kind=AnnotationSceneKind.ANNOTATION, annotations=fake_annotation)
        fake_input = mocker.MagicMock()
        mock_predict = mocker.patch.object(
            OpenVINOSegmentationInferencer, "predict", return_value=(fake_ann_scene, None, fake_input)
        )
        mocker.patch("otx.algorithms.segmentation.tasks.openvino.get_activation_map", return_value=np.zeros((5, 1)))
        mocker.patch.object(ShapeFactory, "shape_produces_valid_crop", return_value=True)
        updated_dataset = self.seg_ov_task.infer(self.dataset)

        mock_predict.assert_called()
        for updated in updated_dataset:
            assert updated.annotation_scene.contains_any([LabelEntity(name="fake", domain="SEGMENTATION")])

    @e2e_pytest_unit
    def test_evaluate(self, mocker):
        result_set = ResultSetEntity(
            model=None,
            ground_truth_dataset=DatasetEntity(),
            prediction_dataset=DatasetEntity(),
        )
        fake_metrics = mocker.patch("otx.api.usecases.evaluation.dice.DiceAverage", autospec=True)
        fake_metrics.get_performance.return_value = Performance(
            score=ScoreMetric(name="fake", value=0.1), dashboard_metrics="mDice"
        )
        mocker.patch.object(MetricsHelper, "compute_dice_averaged_over_pixels", return_value=fake_metrics)
        self.seg_ov_task.evaluate(result_set)

        assert result_set.performance.score.value == 0.1

    @e2e_pytest_unit
    def test_deploy(self, otx_model):
        output_model = copy.deepcopy(otx_model)
        self.seg_ov_task.model.set_data("openvino.bin", b"foo")
        self.seg_ov_task.model.set_data("openvino.xml", b"bar")
        self.seg_ov_task.deploy(output_model)

        assert output_model.exportable_code is not None

    @e2e_pytest_unit
    def test_optimize(self, mocker, otx_model):
        def patch_save_model(model, dir_path, model_name):
            with open(f"{dir_path}/{model_name}.xml", "wb") as f:
                f.write(b"foo")
            with open(f"{dir_path}/{model_name}.bin", "wb") as f:
                f.write(b"bar")

        dataset = generate_otx_dataset()
        output_model = copy.deepcopy(otx_model)
        self.seg_ov_task.model.set_data("openvino.bin", b"foo")
        self.seg_ov_task.model.set_data("openvino.xml", b"bar")
        mocker.patch("otx.algorithms.segmentation.tasks.openvino.load_model", autospec=True)
        mocker.patch("otx.algorithms.segmentation.tasks.openvino.create_pipeline", autospec=True)
        mocker.patch("otx.algorithms.segmentation.tasks.openvino.save_model", new=patch_save_model)
        spy_compress = mocker.spy(otx.algorithms.segmentation.tasks.openvino, "compress_model_weights")
        self.seg_ov_task.optimize(OptimizationType.POT, dataset=dataset, output_model=output_model)

        spy_compress.assert_called_once()
        assert self.seg_ov_task.model.get_data("openvino.bin")
        assert self.seg_ov_task.model.get_data("openvino.xml")
