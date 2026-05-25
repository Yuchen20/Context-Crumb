"""Inference backends for ContextCrumb (ONNX and PyTorch)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Sequence

from contextcrumb.spans import TextToken, tokenize_with_spans


def choose_torch_device(requested: str):
    import torch

    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(requested)


def _softmax(values, axis: int):
    import numpy as np

    shifted = values - np.max(values, axis=axis, keepdims=True)
    exp_values = np.exp(shifted)
    return exp_values / np.sum(exp_values, axis=axis, keepdims=True)


def _resolve_keep_label_id(model: Any) -> int:
    label2id = getattr(getattr(model, "config", None), "label2id", None) or getattr(model, "label2id", None) or {}
    if "KEEP" in label2id:
        return int(label2id["KEEP"])
    for label, label_id in label2id.items():
        if str(label).upper() == "KEEP":
            return int(label_id)
    return 1


def aggregate_word_keep_probabilities(
    word_ids_by_window: Sequence[Sequence[int | None]],
    keep_probs_by_window: Sequence[Sequence[float]],
    word_count: int,
) -> list[float]:
    """Average subtoken keep probabilities across sliding windows."""
    probability_sums = [0.0] * word_count
    probability_counts = [0] * word_count

    for word_ids, keep_probs in zip(word_ids_by_window, keep_probs_by_window):
        for token_index, word_id in enumerate(word_ids):
            if word_id is None or word_id >= word_count:
                continue
            probability_sums[word_id] += float(keep_probs[token_index])
            probability_counts[word_id] += 1

    return [
        probability_sum / probability_count if probability_count else 0.0
        for probability_sum, probability_count in zip(probability_sums, probability_counts)
    ]


class InferenceBackend:
    """Base class defining the backend contract."""

    @property
    def tokenizer(self) -> Any:
        raise NotImplementedError

    @property
    def model(self) -> Any:
        raise NotImplementedError

    @property
    def device(self) -> Any:
        raise NotImplementedError

    def score_keep_probabilities(
        self,
        text: str,
        max_length: int,
        stride: int,
        window_batch_size: int | None,
    ) -> tuple[list[TextToken], list[float], int]:
        raise NotImplementedError


class TorchBackend(InferenceBackend):
    """PyTorch-based token classification inference backend."""

    def __init__(
        self,
        tokenizer: Any,
        model: Any,
        device: Any,
    ) -> None:
        self._tokenizer = tokenizer
        self._model = model
        self._device = device
        self.keep_label_id = _resolve_keep_label_id(model)

    @property
    def tokenizer(self) -> Any:
        return self._tokenizer

    @property
    def model(self) -> Any:
        return self._model

    @property
    def device(self) -> Any:
        return self._device

    @classmethod
    def load(
        cls,
        model_id: str | Path,
        device: str,
        revision: str | None = None,
        cache_dir: str | Path | None = None,
        trust_remote_code: bool = False,
    ) -> TorchBackend:
        from transformers import AutoModelForTokenClassification, AutoTokenizer, PreTrainedTokenizerFast

        resolved_device = choose_torch_device(device)
        model_name_or_path = str(model_id)
        try:
            tokenizer = AutoTokenizer.from_pretrained(
                model_name_or_path,
                revision=revision,
                cache_dir=cache_dir,
                trust_remote_code=trust_remote_code,
                use_fast=True,
            )
        except ValueError as error:
            if "TokenizersBackend" not in str(error):
                raise
            tokenizer_file = Path(model_name_or_path) / "tokenizer.json"
            tokenizer_config_file = Path(model_name_or_path) / "tokenizer_config.json"
            if not tokenizer_file.exists():
                from huggingface_hub import hf_hub_download

                tokenizer_file = Path(
                    hf_hub_download(
                        repo_id=model_name_or_path,
                        filename="tokenizer.json",
                        revision=revision,
                        cache_dir=str(cache_dir) if cache_dir is not None else None,
                    )
                )
                tokenizer_config_file = Path(
                    hf_hub_download(
                        repo_id=model_name_or_path,
                        filename="tokenizer_config.json",
                        revision=revision,
                        cache_dir=str(cache_dir) if cache_dir is not None else None,
                    )
                )
            kwargs = {}
            if tokenizer_config_file.exists():
                tokenizer_config = json.loads(tokenizer_config_file.read_text(encoding="utf-8"))
                kwargs = {
                    key: tokenizer_config[key]
                    for key in ("unk_token", "sep_token", "pad_token", "cls_token", "mask_token")
                    if key in tokenizer_config
                }
            tokenizer = PreTrainedTokenizerFast(tokenizer_file=str(tokenizer_file), **kwargs)
        model = AutoModelForTokenClassification.from_pretrained(
            model_name_or_path,
            revision=revision,
            cache_dir=cache_dir,
            trust_remote_code=trust_remote_code,
        ).to(resolved_device)
        model.eval()
        return cls(tokenizer, model, resolved_device)

    def score_keep_probabilities(
        self,
        text: str,
        max_length: int,
        stride: int,
        window_batch_size: int | None,
    ) -> tuple[list[TextToken], list[float], int]:
        import torch

        tokens = tokenize_with_spans(text)
        if not tokens:
            return [], [], 0

        encoded = self._tokenizer(
            [token.text for token in tokens],
            is_split_into_words=True,
            truncation=True,
            padding="max_length",
            max_length=max_length,
            stride=stride,
            return_overflowing_tokens=True,
            return_tensors="pt",
        )
        window_count = len(encoded["input_ids"])
        word_ids_by_window = [
            encoded.word_ids(batch_index=batch_index)
            for batch_index in range(window_count)
        ]
        input_names = set(getattr(self._tokenizer, "model_input_names", ("input_ids", "attention_mask")))
        forward_parameters = set(inspect.signature(self._model.forward).parameters)
        model_inputs = {
            key: value.to(self._device)
            for key, value in encoded.items()
            if key in input_names and key in forward_parameters and hasattr(value, "to")
        }

        keep_probs_by_window = []
        batch_size = window_batch_size or window_count
        with torch.inference_mode():
            for start in range(0, window_count, batch_size):
                end = min(start + batch_size, window_count)
                batch_inputs = {key: value[start:end] for key, value in model_inputs.items()}
                logits = self._model(**batch_inputs).logits
                batch_probs = torch.softmax(logits, dim=-1)[:, :, self.keep_label_id].detach().cpu().tolist()
                keep_probs_by_window.extend(batch_probs)

        return tokens, aggregate_word_keep_probabilities(word_ids_by_window, keep_probs_by_window, len(tokens)), window_count


class OnnxTokenClassifier:
    """Wrapper around ONNX Runtime InferenceSession to mimic a classification model config."""

    def __init__(self, *, session: Any, config_path: Path) -> None:
        self.session = session
        self.input_names = {input_meta.name for input_meta in session.get_inputs()}
        self.label2id: dict[str, int] = {"DELETE": 0, "KEEP": 1}
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            label2id = config.get("label2id")
            if isinstance(label2id, dict):
                self.label2id = {str(label): int(label_id) for label, label_id in label2id.items()}

    def run(self, inputs: dict[str, Any]):
        outputs = self.session.run(None, inputs)
        return outputs[0]


class OnnxBackend(InferenceBackend):
    """ONNX Runtime-based token classification inference backend."""

    def __init__(
        self,
        tokenizer: Any,
        model: OnnxTokenClassifier,
        device: str,
    ) -> None:
        self._tokenizer = tokenizer
        self._model = model
        self._device = device
        self.keep_label_id = _resolve_keep_label_id(model)

    @property
    def tokenizer(self) -> Any:
        return self._tokenizer

    @property
    def model(self) -> Any:
        return self._model

    @property
    def device(self) -> Any:
        return self._device

    @classmethod
    def load(
        cls,
        model_id: str | Path,
        device: str,
        revision: str | None = None,
        cache_dir: str | Path | None = None,
    ) -> OnnxBackend:
        import onnxruntime as ort
        from huggingface_hub import snapshot_download
        from tokenizers import Tokenizer

        model_path = Path(model_id)
        if not model_path.exists():
            local_dir_root = Path(cache_dir) if cache_dir is not None else Path.home() / ".cache" / "contextcrumb"
            safe_revision = revision or "main"
            local_dir = local_dir_root / str(model_id).replace("/", "--") / safe_revision.replace("/", "--")
            model_path = Path(
                snapshot_download(
                    repo_id=str(model_id),
                    revision=revision,
                    local_dir=str(local_dir),
                    allow_patterns=["onnx/*", "config.json"],
                )
            )

        onnx_dir = model_path / "onnx"
        if (onnx_dir / "model.onnx").exists():
            runtime_dir = onnx_dir
        else:
            runtime_dir = model_path

        onnx_path = runtime_dir / "model.onnx"
        tokenizer_path = runtime_dir / "tokenizer.json"
        if not onnx_path.exists() or not tokenizer_path.exists():
            raise FileNotFoundError(
                "ONNX backend requires model.onnx and tokenizer.json, either at the model root or under onnx/."
            )

        requested = device.lower()
        available = ort.get_available_providers()
        if requested in {"auto", "cpu"}:
            providers = ["CPUExecutionProvider"]
        elif requested in {"cuda", "gpu"}:
            if "CUDAExecutionProvider" not in available:
                raise RuntimeError("onnxruntime GPU provider is not installed; use device='cpu' or install onnxruntime-gpu.")
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            raise ValueError("ONNX backend supports device='auto', 'cpu', or 'cuda'.")

        session = ort.InferenceSession(str(onnx_path), providers=providers)
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        model = OnnxTokenClassifier(session=session, config_path=model_path / "config.json")
        return cls(tokenizer, model, providers[0])

    def score_keep_probabilities(
        self,
        text: str,
        max_length: int,
        stride: int,
        window_batch_size: int | None,
    ) -> tuple[list[TextToken], list[float], int]:
        import numpy as np

        tokens = tokenize_with_spans(text)
        if not tokens:
            return [], [], 0

        self._tokenizer.enable_truncation(max_length=max_length, stride=stride)
        pad_token_id = self._tokenizer.token_to_id("[PAD]")
        if pad_token_id is None:
            pad_token_id = 0
        self._tokenizer.enable_padding(length=max_length, pad_id=pad_token_id, pad_token="[PAD]")
        encoding = self._tokenizer.encode([token.text for token in tokens], is_pretokenized=True)
        windows = [encoding, *encoding.overflowing]
        window_count = len(windows)
        word_ids_by_window = [window.word_ids for window in windows]

        input_ids = np.asarray([window.ids for window in windows], dtype=np.int64)
        attention_mask = np.asarray([window.attention_mask for window in windows], dtype=np.int64)
        keep_probs_by_window = []
        batch_size = window_batch_size or window_count
        input_names = self._model.input_names
        for start in range(0, window_count, batch_size):
            end = min(start + batch_size, window_count)
            model_inputs = {}
            if "input_ids" in input_names:
                model_inputs["input_ids"] = input_ids[start:end]
            if "attention_mask" in input_names:
                model_inputs["attention_mask"] = attention_mask[start:end]
            logits = self._model.run(model_inputs)
            probs = _softmax(logits, axis=-1)[:, :, self.keep_label_id]
            keep_probs_by_window.extend(probs.tolist())

        return tokens, aggregate_word_keep_probabilities(word_ids_by_window, keep_probs_by_window, len(tokens)), window_count


def load_backend(
    backend_name: str,
    model_id: str | Path,
    device: str,
    revision: str | None = None,
    cache_dir: str | Path | None = None,
    trust_remote_code: bool = False,
) -> InferenceBackend:
    """Factory to load the requested backend."""
    if backend_name == "onnx":
        return OnnxBackend.load(
            model_id=model_id,
            device=device,
            revision=revision,
            cache_dir=cache_dir,
        )
    elif backend_name == "torch":
        return TorchBackend.load(
            model_id=model_id,
            device=device,
            revision=revision,
            cache_dir=cache_dir,
            trust_remote_code=trust_remote_code,
        )
    else:
        raise ValueError(f"Unknown backend: {backend_name}")
