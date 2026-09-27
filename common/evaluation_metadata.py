"""
Typed metadata schema for MAIRE evaluation framework.

Provides type-safe access to evaluation metadata dictionary with:
- IDE autocomplete for common keys
- Dynamic key addition support for device-specific extensions
- Dict-style and attribute-style access
- Type hints for better code readability

Usage:
    from common.evaluation_metadata import MetadataDict
    
    metadata = MetadataDict()
    metadata.eval_id = "q00020"  # IDE autocomplete
    metadata["question_type"] = "online_samsung_camera_click"  # Dict style
    metadata.jinju_image_captured = True  # Dynamic key
"""

from __future__ import annotations
from typing import Any, Literal


# =============================================================================
# TypedDict Definitions for Type Hints
# =============================================================================

from typing import TypedDict, NotRequired, Optional


class CoreMetadata(TypedDict, total=False):
    """Core metadata present in ALL evaluations."""
    # Evaluation context
    eval_id: str
    eval_type: Literal["APP_EVAL_TASK", "QA_TASK", "Visual_QA_TASK", "Hallucination_TASK"]
    question_type: str
    question: str
    reference: str
    
    # Media (base64 encoded)
    encoded_audio: str
    encoded_image: str
    encoded_app_screenshot: str


class JinjuMetadata(TypedDict, total=False):
    """Jinju-specific metadata (glasses device)."""
    jinju_image_captured: bool
    jinju_image_path: Optional[str]
    jinju_video_captured: bool
    jinju_video_path: Optional[str]
    jinju_invoke_ts: str


class DeviceStateMetadata(TypedDict, total=False):
    """Device state metadata (when DeviceInfoMixin used)."""
    device_info_pre: dict[str, Any]
    device_info_post: dict[str, Any]
    device_info_state: dict[str, Any]
    device_info_pre_path: str
    device_info_post_path: str
    companion_device: str
    s25_device_id: str


class AppStateMetadata(TypedDict, total=False):
    """App state metadata (when StateCollectMixin used)."""
    app_state: dict[str, Any]  # {method, verified, rating, analysis, actual_state, expected}
    app_state_pre: dict[str, Any]
    xrclaw_state: dict[str, Any]
    xrclaw_state_pre: dict[str, Any]
    pre_state_screenshots: list[str]  # List of paths to pre-state screenshots
    post_state_screenshots: list[str]  # List of paths to post-state screenshots


class DeviceCommandMetadata(TypedDict, total=False):
    """Device command metadata (when DeviceCommandMixin used)."""
    device_command_result: dict[str, Any]


class JudgeOutputMetadata(TypedDict, total=False):
    """Judge output metadata (added by judge_worker)."""
    rating: int
    analysis: str
    entropy_metrics: dict[str, float]
    judge_method: Literal["vlm", "deterministic", "error_empty_response", "skipped"]
    judge_prompt_path: str
    error_type: int
    response_time: float
    duration: float


# Combined type for comprehensive type hints
EvaluationMetadata = (
    CoreMetadata 
    | JinjuMetadata 
    | DeviceStateMetadata 
    | AppStateMetadata 
    | DeviceCommandMetadata 
    | JudgeOutputMetadata
)


# =============================================================================
# Runtime MetadataDict Class
# =============================================================================

class MetadataDict(dict):
    """
    Extensible metadata dictionary with type-hinted properties.
    
    Features:
    - Supports dict-style access: metadata["eval_id"]
    - Supports attribute access: metadata.eval_id
    - Allows dynamic key addition: metadata.new_key = value
    - IDE autocomplete for common keys
    - Works seamlessly with existing code expecting dict
    
    Usage:
        metadata = MetadataDict()
        metadata.eval_id = "q00020"  # Attribute style with autocomplete
        metadata["question_type"] = "online_samsung_camera_click"  # Dict style
        metadata.jinju_image_captured = True  # Dynamic key (Jinju-specific)
        
        # Fluent API
        metadata.add("eval_id", "q00020").add("eval_type", "APP_EVAL_TASK")
        
        # Dict compatibility
        eval_id = metadata.get("eval_id", "")
        for key, value in metadata.items():
            ...
    """
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._typed_keys: set[str] = set()
    
    def __getattr__(self, key: str) -> Any:
        """Enable attribute-style access: metadata.eval_id"""
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' has no key '{key}'")
    
    def __setattr__(self, key: str, value: Any) -> None:
        """Enable attribute-style assignment: metadata.eval_id = 'q00020'"""
        if key.startswith("_"):
            super().__setattr__(key, value)
        else:
            self[key] = value
            self._typed_keys.add(key)
    
    def __delattr__(self, key: str) -> None:
        """Enable attribute-style deletion: del metadata.eval_id"""
        if key.startswith("_"):
            super().__delattr__(key)
        else:
            del self[key]
    
    # =========================================================================
    # Type-hinted Properties for IDE Autocomplete
    # =========================================================================
    
    # --- Core Metadata ---
    @property
    def eval_id(self) -> str:
        """Unique evaluation ID (e.g., 'q00020')."""
        return self.get("eval_id", "")
    
    @eval_id.setter
    def eval_id(self, value: str) -> None:
        self["eval_id"] = value
    
    @property
    def eval_type(self) -> str:
        """Task type: APP_EVAL_TASK, QA_TASK, Visual_QA_TASK, Hallucination_TASK."""
        return self.get("eval_type", "")
    
    @eval_type.setter
    def eval_type(self, value: str) -> None:
        self["eval_type"] = value
    
    @property
    def question_type(self) -> str:
        """4-part format: <connectivity>_<group>_<feature>_<action>."""
        return self.get("question_type", "")
    
    @question_type.setter
    def question_type(self, value: str) -> None:
        self["question_type"] = value
    
    @property
    def question(self) -> str:
        """User's original query."""
        return self.get("question", "")
    
    @question.setter
    def question(self, value: str) -> None:
        self["question"] = value
    
    @property
    def reference(self) -> str:
        """Ground truth answer."""
        return self.get("reference", "")
    
    @reference.setter
    def reference(self, value: str) -> None:
        self["reference"] = value
    
    @property
    def encoded_audio(self) -> str:
        """Base64 encoded AI response audio."""
        return self.get("encoded_audio", "")
    
    @encoded_audio.setter
    def encoded_audio(self, value: str) -> None:
        self["encoded_audio"] = value
    
    @property
    def encoded_image(self) -> str:
        """Base64 encoded Jinju screen image."""
        return self.get("encoded_image", "")
    
    @encoded_image.setter
    def encoded_image(self, value: str) -> None:
        self["encoded_image"] = value
    
    @property
    def encoded_app_screenshot(self) -> str:
        """Base64 encoded companion app screenshot."""
        return self.get("encoded_app_screenshot", "")
    
    @encoded_app_screenshot.setter
    def encoded_app_screenshot(self, value: str) -> None:
        self["encoded_app_screenshot"] = value
    
    # --- Jinju-specific ---
    @property
    def jinju_image_captured(self) -> bool:
        """True if photo was captured and saved (Jinju only)."""
        return self.get("jinju_image_captured", False)
    
    @jinju_image_captured.setter
    def jinju_image_captured(self, value: bool) -> None:
        self["jinju_image_captured"] = value
    
    @property
    def jinju_image_path(self) -> Optional[str]:
        """Path to captured photo on Jinju (Jinju only)."""
        return self.get("jinju_image_path")
    
    @jinju_image_path.setter
    def jinju_image_path(self, value: Optional[str]) -> None:
        self["jinju_image_path"] = value
    
    @property
    def jinju_video_captured(self) -> bool:
        """True if video was recorded and saved (Jinju only)."""
        return self.get("jinju_video_captured", False)
    
    @jinju_video_captured.setter
    def jinju_video_captured(self, value: bool) -> None:
        self["jinju_video_captured"] = value
    
    @property
    def jinju_video_path(self) -> Optional[str]:
        """Path to captured video on Jinju (Jinju only)."""
        return self.get("jinju_video_path")
    
    @jinju_video_path.setter
    def jinju_video_path(self, value: Optional[str]) -> None:
        self["jinju_video_path"] = value
    
    @property
    def jinju_invoke_ts(self) -> str:
        """Timestamp when Jinju was invoked (Jinju only)."""
        return self.get("jinju_invoke_ts", "")
    
    @jinju_invoke_ts.setter
    def jinju_invoke_ts(self, value: str) -> None:
        self["jinju_invoke_ts"] = value
    
    # --- Device State ---
    @property
    def device_info_pre(self) -> dict[str, Any]:
        """Device state BEFORE task (battery, volume, DND, connectivity)."""
        return self.get("device_info_pre", {})
    
    @device_info_pre.setter
    def device_info_pre(self, value: dict[str, Any]) -> None:
        self["device_info_pre"] = value
    
    @property
    def device_info_post(self) -> dict[str, Any]:
        """Device state AFTER task."""
        return self.get("device_info_post", {})
    
    @device_info_post.setter
    def device_info_post(self, value: dict[str, Any]) -> None:
        self["device_info_post"] = value
    
    @property
    def device_info_state(self) -> dict[str, Any]:
        """Generic device info state (legacy)."""
        return self.get("device_info_state", {})
    
    @device_info_state.setter
    def device_info_state(self, value: dict[str, Any]) -> None:
        self["device_info_state"] = value
    
    @property
    def device_info_pre_path(self) -> str:
        """Path to pre-state JSON file."""
        return self.get("device_info_pre_path", "")
    
    @device_info_pre_path.setter
    def device_info_pre_path(self, value: str) -> None:
        self["device_info_pre_path"] = value
    
    @property
    def device_info_post_path(self) -> str:
        """Path to post-state JSON file."""
        return self.get("device_info_post_path", "")
    
    @device_info_post_path.setter
    def device_info_post_path(self, value: str) -> None:
        self["device_info_post_path"] = value
    
    @property
    def companion_device(self) -> str:
        """S25 device ID."""
        return self.get("companion_device", "")
    
    @companion_device.setter
    def companion_device(self, value: str) -> None:
        self["companion_device"] = value
    
    @property
    def s25_device_id(self) -> str:
        """Alternative S25 device ID."""
        return self.get("s25_device_id", "")
    
    @s25_device_id.setter
    def s25_device_id(self, value: str) -> None:
        self["s25_device_id"] = value
    
    # --- App State ---
    @property
    def app_state(self) -> dict[str, Any]:
        """Post-task app state from state collector."""
        return self.get("app_state", {})
    
    @app_state.setter
    def app_state(self, value: dict[str, Any]) -> None:
        self["app_state"] = value
    
    @property
    def app_state_pre(self) -> dict[str, Any]:
        """Pre-task app state."""
        return self.get("app_state_pre", {})
    
    @app_state_pre.setter
    def app_state_pre(self, value: dict[str, Any]) -> None:
        self["app_state_pre"] = value
    
    @property
    def xrclaw_state(self) -> dict[str, Any]:
        """XRClaw state (backward compat)."""
        return self.get("xrclaw_state", {})
    
    @xrclaw_state.setter
    def xrclaw_state(self, value: dict[str, Any]) -> None:
        self["xrclaw_state"] = value
    
    @property
    def xrclaw_state_pre(self) -> dict[str, Any]:
        """Pre-task XRClaw state."""
        return self.get("xrclaw_state_pre", {})
    
    @xrclaw_state_pre.setter
    def xrclaw_state_pre(self, value: dict[str, Any]) -> None:
        self["xrclaw_state_pre"] = value
    
    @property
    def app_screenshot_path(self) -> str:
        """Path to companion app screenshot."""
        return self.get("app_screenshot_path", "")
    
    @app_screenshot_path.setter
    def app_screenshot_path(self, value: str) -> None:
        self["app_screenshot_path"] = value
    
    @property
    def image_path(self) -> str:
        """Path to Jinju screen image."""
        return self.get("image_path", "")
    
    @image_path.setter
    def image_path(self, value: str) -> None:
        self["image_path"] = value
    
    # --- Device Command ---
    @property
    def device_command_result(self) -> dict[str, Any]:
        """Result of device command execution."""
        return self.get("device_command_result", {})
    
    @device_command_result.setter
    def device_command_result(self, value: dict[str, Any]) -> None:
        self["device_command_result"] = value
    
    # --- Judge Output ---
    @property
    def rating(self) -> int:
        """Evaluation score (0-5)."""
        return self.get("rating", 0)
    
    @rating.setter
    def rating(self, value: int) -> None:
        self["rating"] = value
    
    @property
    def analysis(self) -> str:
        """Judge's reasoning."""
        return self.get("analysis", "")
    
    @analysis.setter
    def analysis(self, value: str) -> None:
        self["analysis"] = value
    
    @property
    def entropy_metrics(self) -> dict[str, float]:
        """Entropy metrics: {entropy, surprisal, curvature, entropy_delta}."""
        return self.get("entropy_metrics", {})
    
    @entropy_metrics.setter
    def entropy_metrics(self, value: dict[str, float]) -> None:
        self["entropy_metrics"] = value
    
    @property
    def judge_method(self) -> str:
        """Judge method: vlm, deterministic, error_empty_response, skipped."""
        return self.get("judge_method", "")
    
    @judge_method.setter
    def judge_method(self, value: str) -> None:
        self["judge_method"] = value
    
    @property
    def judge_prompt_path(self) -> str:
        """Path to saved judge prompt for debugging."""
        return self.get("judge_prompt_path", "")
    
    @judge_prompt_path.setter
    def judge_prompt_path(self, value: str) -> None:
        self["judge_prompt_path"] = value
    
    @property
    def error_type(self) -> int:
        """Error type: 0=none, 1=empty response."""
        return self.get("error_type", 0)
    
    @error_type.setter
    def error_type(self, value: int) -> None:
        self["error_type"] = value
    
    @property
    def response_time(self) -> float:
        """STT response start time."""
        return self.get("response_time", 0.0)
    
    @response_time.setter
    def response_time(self, value: float) -> None:
        self["response_time"] = value
    
    @property
    def duration(self) -> float:
        """Audio duration in seconds."""
        return self.get("duration", 0.0)
    
    @duration.setter
    def duration(self, value: float) -> None:
        self["duration"] = value
    
    # --- Special Flags ---
    @property
    def skip(self) -> bool:
        """True if automated evaluation is not supported."""
        return self.get("skip", False)
    
    @skip.setter
    def skip(self, value: bool) -> None:
        self["skip"] = value
    
    @property
    def extra_logs(self) -> dict[str, Any]:
        """Additional log data."""
        return self.get("extra_logs", {})
    
    @extra_logs.setter
    def extra_logs(self, value: dict[str, Any]) -> None:
        self["extra_logs"] = value
    
    # =========================================================================
    # Fluent API
    # =========================================================================
    
    def add(self, key: str, value: Any) -> MetadataDict:
        """
        Add a key-value pair and return self for chaining.
        
        Usage:
            metadata.add("eval_id", "q00020").add("eval_type", "APP_EVAL_TASK")
        """
        self[key] = value
        return self
    
    def add_many(self, **kwargs: Any) -> MetadataDict:
        """
        Add multiple key-value pairs and return self for chaining.
        
        Usage:
            metadata.add_many(eval_id="q00020", eval_type="APP_EVAL_TASK")
        """
        self.update(kwargs)
        return self
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def get_nested(self, key: str, default: Any = None) -> Any:
        """
        Get a nested value using dot notation.
        
        Usage:
            metadata.get_nested("device_info_pre.battery")  # Returns battery level
        """
        keys = key.split(".")
        value: Any = self
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value
    
    def to_dict(self) -> dict[str, Any]:
        """Return as plain dict (for JSON serialization)."""
        return dict(self)
    
    def copy(self) -> MetadataDict:
        """Return a shallow copy."""
        return MetadataDict(super().copy())
