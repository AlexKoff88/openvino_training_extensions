# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

from otx.mpa.det.trainer import DetectionTrainer
from otx.mpa.registry import STAGES
from otx.mpa.utils.logger import get_logger

from .stage import SemiSLDetectionStage

logger = get_logger()


@STAGES.register_module()
class SemiSLDetectionTrainer(SemiSLDetectionStage, DetectionTrainer):
    def __init__(self, **kwargs):
        SemiSLDetectionStage.__init__(self, **kwargs)
