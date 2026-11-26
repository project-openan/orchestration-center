# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Opt-in retrieval validation is local configuration validation, not a probe."""
from unittest.mock import patch

import pytest

from common.llm.config.llm_config import ModelConfig
from orchestrate.core import psop_vector_index as vector


def test_disabled_retrieval_does_not_require_model_configuration():
    with patch("common.llm.config.llm_config.get_model_config") as model:
        vector.validate_retrieval_config({"retrieval.vector.enabled": "false"})
    model.assert_not_called()


@pytest.mark.parametrize("missing", ["embed", "rerank"])
def test_enabled_retrieval_rejects_missing_required_capability(missing):
    with patch("common.llm.config.llm_config.get_model_config", side_effect=lambda cap: None if cap == missing
               else ModelConfig(model="synthetic", url="https://example.invalid/model")):
        with pytest.raises(ValueError, match=missing):
            vector.validate_retrieval_config({"retrieval.vector.enabled": "true", "retrieval.vector.rerank": "true"})


def test_keyless_embedding_configuration_is_valid_without_network():
    config = ModelConfig(model="synthetic", url="http://localhost:1234/embeddings")
    with patch("common.llm.config.llm_config.get_model_config", return_value=config), \
         patch("common.llm.llm.GenericLLM", side_effect=AssertionError("Must not create network clients")):
        vector.validate_retrieval_config({"retrieval.vector.enabled": "true"})
